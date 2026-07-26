from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from services import servers


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.split("."):
        digits = "".join(character for character in piece if character.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _required_java_major(version: str) -> int:
    parsed = _version_tuple(version)
    # Mojang calendar-style IDs (25.x / 26.x / …) are not classic 1.x versions.
    # Minecraft 26.x ships class-file 69 → needs Java 25+.
    if parsed and parsed[0] >= 25 and parsed[0] < 100:
        return 25
    if parsed and parsed <= (1, 16, 5):
        return 8
    if parsed and parsed < (1, 20, 5):
        return 17
    return 21


def _max_java_major(version: str) -> int | None:
    """Old LaunchWrapper Forge breaks on Java 9+ with ClassCastException."""
    parsed = _version_tuple(version)
    if parsed and parsed[0] >= 25 and parsed[0] < 100:
        return None
    if parsed and parsed <= (1, 12, 2):
        return 8
    if parsed and parsed < (1, 17):
        return 16
    return None


def _java_candidates(version: str) -> list[str]:
    configured = os.environ.get("MINEBOX_JAVA")
    candidates: list[str] = [configured] if configured else []
    major = _required_java_major(version)
    maximum = _max_java_major(version)
    if maximum is None:
        majors = list(range(major, major + 3))
    else:
        majors = list(range(major, maximum + 1))

    for value in majors:
        candidates.extend(
            [
                f"/opt/java/temurin-{value}/bin/java",
                f"/opt/java/jdk-{value}/bin/java",
                f"/usr/lib/jvm/java-{value}-openjdk-arm64/bin/java",
                f"/usr/lib/jvm/java-{value}-openjdk-armhf/bin/java",
                f"/usr/lib/jvm/java-{value}-openjdk-amd64/bin/java",
                f"/usr/lib/jvm/temurin-{value}-jdk-arm64/bin/java",
                f"/usr/lib/jvm/temurin-{value}-jre-arm64/bin/java",
                f"java{value}",
            ]
        )

    candidates.append("java")
    return candidates


def _java_major_version(java: str) -> int | None:
    try:
        result = subprocess.run(
            [java, "-version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = f"{result.stderr}\n{result.stdout}"
    match = re.search(r'version "(?P<ver>[^"]+)"', text)
    if not match:
        match = re.search(r"version (?P<ver>\d+(\.\d+)*)", text)
    if not match:
        return None
    ver = match.group("ver")
    if ver.startswith("1."):
        pieces = ver.split(".")
        return int(pieces[1]) if len(pieces) > 1 else None
    return int(ver.split(".")[0])


def _ensure_java_installed(version: str) -> None:
    """Install Java 8/17/21 as needed (Temurin fallback for missing apt pkgs)."""
    required = _required_java_major(version)
    maximum = _max_java_major(version)
    script = Path(__file__).resolve().parents[1] / "scripts" / "minebox_ensure_java.py"
    helpers = [
        [
            "sudo",
            "-n",
            "/usr/local/sbin/minebox-ensure-java",
            "--min",
            str(required),
        ],
        [
            "sudo",
            "-n",
            "/usr/bin/python3",
            "/opt/minebox/scripts/minebox_ensure_java.py",
            "--min",
            str(required),
        ],
        [
            "sudo",
            "-n",
            "/usr/bin/python3",
            str(script),
            "--min",
            str(required),
        ],
    ]
    if maximum is not None:
        for command in helpers:
            command.extend(["--max", str(maximum)])

    errors: list[str] = []
    for command in helpers:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=900,
            )
        except (OSError, subprocess.SubprocessError) as error:
            errors.append(f"{command[0]}: {error}")
            continue
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode == 0 and stdout:
            return
        if result.returncode == 0:
            return
        detail = stderr or stdout or f"exit {result.returncode}"
        errors.append(f"{' '.join(command[:4])}... -> {detail[:300]}")

    if errors:
        raise RuntimeError(
            "Automatic Java install failed. "
            + " | ".join(errors[:2])
        )


def _find_java(version: str) -> str:
    required = _required_java_major(version)
    maximum = _max_java_major(version)

    def _scan() -> str | None:
        compatible: list[tuple[int, str]] = []
        for candidate in _java_candidates(version):
            if not candidate:
                continue
            if "/" in candidate:
                path = Path(candidate)
                if not (path.is_file() and os.access(path, os.X_OK)):
                    continue
                resolved = str(path)
            else:
                found = shutil.which(candidate)
                if not found:
                    continue
                resolved = found

            major = _java_major_version(resolved)
            if major is None:
                continue
            if major < required:
                continue
            if maximum is not None and major > maximum:
                continue
            compatible.append((major, resolved))
        if not compatible:
            return None
        compatible.sort(key=lambda item: item[0], reverse=True)
        return compatible[0][1]

    found = _scan()
    if found:
        return found

    try:
        _ensure_java_installed(version)
    except RuntimeError as error:
        raise RuntimeError(
            f"Minecraft {version} needs Java {required}"
            + (f"-{maximum}" if maximum is not None and maximum != required else "")
            + f". {error}"
        ) from error

    found = _scan()
    if found:
        return found

    if maximum is not None:
        raise RuntimeError(
            f"Minecraft {version} needs Java {required}"
            + (f"-{maximum}" if maximum != required else "")
            + ". Install still did not provide a usable runtime. "
            f"On the Pi run: sudo python3 /opt/minebox/scripts/minebox_ensure_java.py "
            f"--min {required}"
            + (f" --max {maximum}" if maximum is not None else "")
        )
    raise RuntimeError(
        f"No compatible Java runtime was found for Minecraft {version} "
        f"(needs Java {required}+)."
    )


def _write_user_jvm_args(server_dir: Path, memory_gb: int) -> Path:
    """Keep Forge/NeoForge memory settings in the official JVM argfile."""
    path = server_dir / "user_jvm_args.txt"
    # Cap startup heap a bit for Pi stability; -Xmx still follows the setting.
    memory = max(1, int(memory_gb))
    xms = max(1, min(memory, 2))
    memory_lines = [f"-Xms{xms}G", f"-Xmx{memory}G"]

    existing = ""
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""

    kept: list[str] = []
    for line in existing.splitlines():
        stripped = line.strip()
        if re.match(r"^-Xm[sx]\S+", stripped):
            continue
        kept.append(line.rstrip())

    while kept and kept[-1] == "":
        kept.pop()
    if kept and not kept[-1].startswith("#"):
        kept.append("")
    kept.extend(memory_lines)
    kept.append("")
    path.write_text("\n".join(kept), encoding="utf-8")
    return path


def _find_forge_unix_args(server_dir: Path, instance: servers.ServerInstance) -> Path | None:
    configured = (instance.main_jar or "").strip()
    if configured.startswith("@"):
        candidate = server_dir / configured[1:]
        if candidate.is_file():
            return candidate

    marker = server_dir / ".minebox-forge-args"
    if marker.is_file():
        relative = marker.read_text(encoding="utf-8").strip()
        if relative:
            candidate = server_dir / relative
            if candidate.is_file():
                return candidate

    matches = sorted(
        (server_dir / "libraries").rglob("unix_args.txt")
    ) if (server_dir / "libraries").is_dir() else []
    forge_matches = [
        path
        for path in matches
        if "minecraftforge" in path.as_posix() or "neoforged" in path.as_posix()
    ]
    if forge_matches:
        return forge_matches[-1]
    return None


def _forge_jars(server_dir: Path) -> list[Path]:
    jars: list[Path] = []
    for path in sorted(server_dir.glob("forge-*.jar")):
        name = path.name.lower()
        if "installer" in name:
            continue
        jars.append(path)
    return jars


def _find_legacy_forge_jar(
    server_dir: Path,
    instance: servers.ServerInstance,
) -> Path | None:
    jars = _forge_jars(server_dir)
    if not jars:
        return None

    # Prefer an exact forge-<mc>-<build>.jar when we know the versions.
    version = (instance.version or "").strip()
    build = (instance.loader_version or "").strip()
    if version and build:
        exact = server_dir / f"forge-{version}-{build}.jar"
        if exact.is_file():
            return exact
        # Promo values sometimes already include the MC version prefix.
        if build.startswith(f"{version}-"):
            exact = server_dir / f"forge-{build}.jar"
            if exact.is_file():
                return exact

    # Prefer non-universal / non-shim names last; main server jar first.
    def rank(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        if "shim" in name:
            return (2, name)
        if "universal" in name:
            return (1, name)
        return (0, name)

    return sorted(jars, key=rank)[0]


def _write_launch_record(server_dir: Path, command: list[str], java: str) -> None:
    log_dir = server_dir / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "minebox-launcher.log").write_text(
            "java="
            + java
            + "\ncommand="
            + " ".join(command)
            + "\ncwd="
            + str(server_dir)
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _forge_command(
    server_dir: Path,
    instance: servers.ServerInstance,
    java: str,
) -> list[str] | None:
    loader = (instance.loader or "").strip().lower()
    unix_args = _find_forge_unix_args(server_dir, instance)
    run_sh = server_dir / "run.sh"
    legacy_jar = _find_legacy_forge_jar(server_dir, instance)
    looks_like_forge = (
        loader in {"forge", "neoforge"}
        or unix_args is not None
        or run_sh.is_file()
        or (server_dir / ".minebox-forge-args").is_file()
        or (server_dir / ".minebox-forge-jar").is_file()
        or legacy_jar is not None
        or any(server_dir.glob("forge-*-shim.jar"))
        or (server_dir / "libraries" / "net" / "minecraftforge").is_dir()
    )
    if not looks_like_forge:
        return None

    # Keep registry honest so the dashboard shows Forge, not Vanilla.
    if loader not in {"forge", "neoforge"}:
        try:
            servers.update_server_launch(
                instance.server_id,
                loader="forge",
                main_jar=(
                    f"@{unix_args.relative_to(server_dir).as_posix()}"
                    if unix_args is not None
                    else (legacy_jar.name if legacy_jar is not None else None)
                ),
            )
        except Exception:
            pass

    _write_user_jvm_args(server_dir, instance.memory_gb)
    memory = max(1, int(instance.memory_gb))

    # Prefer a direct Java launch. Official run.sh often exits immediately on Pi
    # because of its `shim.jar --onlyCheckJava || exit 1` gate.
    if unix_args is not None:
        user_jvm = server_dir / "user_jvm_args.txt"
        return [
            java,
            f"@{user_jvm.name}",
            f"@{unix_args.relative_to(server_dir).as_posix()}",
            "nogui",
        ]

    marker = server_dir / ".minebox-forge-jar"
    if marker.is_file():
        named = marker.read_text(encoding="utf-8").strip()
        if named and (server_dir / named).is_file():
            return [
                java,
                f"-Xms{min(memory, 2)}G",
                f"-Xmx{memory}G",
                "-jar",
                named,
                "nogui",
            ]

    # Legacy / mid Forge (1.12 and many 1.13-1.16 installs): launch the Forge jar,
    # never vanilla server.jar (that reports brand "vanilla" in Minecraft).
    if legacy_jar is not None:
        return [
            java,
            f"-Xms{min(memory, 2)}G",
            f"-Xmx{memory}G",
            "-jar",
            legacy_jar.name,
            "nogui",
        ]

    if run_sh.is_file():
        text = run_sh.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"@(\S*libraries/\S+/unix_args\.txt)", text)
        if match:
            args_rel = match.group(1)
            safe = server_dir / "minebox-forge-run.sh"
            safe.write_text(
                "#!/bin/bash\n"
                "set -e\n"
                f'exec "{java}" @user_jvm_args.txt @{args_rel} nogui\n',
                encoding="utf-8",
            )
            try:
                os.chmod(safe, 0o755)
            except OSError:
                pass
            return ["/bin/bash", str(safe)]

    raise RuntimeError(
        "This Forge install is missing its Forge server jar / unix_args.txt. "
        "Reinstall Forge from setup, or verify forge-*.jar exists in the server folder."
    )


def _resolve_main_jar(server_dir: Path, instance: servers.ServerInstance) -> str:
    legacy_jar = _find_legacy_forge_jar(server_dir, instance)
    forge_installed = legacy_jar is not None or (
        server_dir / "libraries" / "net" / "minecraftforge"
    ).is_dir()

    configured = (instance.main_jar or "server.jar").strip()
    if configured.startswith("@"):
        candidate = server_dir / configured[1:]
        if candidate.is_file():
            return configured

    if forge_installed and legacy_jar is not None:
        return legacy_jar.name

    if configured and not configured.startswith("@") and (server_dir / configured).is_file():
        return configured

    for name in (
        "fabric-server-launch.jar",
        "server.jar",
    ):
        if (server_dir / name).is_file():
            return name

    raise RuntimeError(
        f"The active server '{instance.name}' does not have a launchable server jar."
    )


def ensure_runtime_for_active() -> str:
    """Make sure the active server's Java is installed; return its path."""
    instance = servers.active_server()
    if instance is None:
        raise RuntimeError("No active Minecraft server is selected.")
    return _find_java(instance.version)


def build_command() -> tuple[Path, list[str], dict[str, str] | None]:
    instance = servers.active_server()
    if instance is None:
        raise RuntimeError("No active Minecraft server is selected.")

    server_dir = Path(instance.directory)
    if not server_dir.is_dir():
        raise RuntimeError(f"Server directory does not exist: {server_dir}")

    # Forge/Minecraft exit immediately when eula is false.
    eula = server_dir / "eula.txt"
    try:
        text = eula.read_text(encoding="utf-8") if eula.is_file() else ""
    except OSError:
        text = ""
    if "eula=true" not in text.lower():
        eula.write_text("eula=true\n", encoding="utf-8")

    # Keep RCON enabled — Forge first-run often strips it from server.properties.
    try:
        from services import rcon as rcon_service

        rcon_service.ensure_properties(server_dir)
    except Exception:
        pass

    java = _find_java(instance.version)
    forge_command = _forge_command(server_dir, instance, java)
    if forge_command is not None:
        _write_launch_record(server_dir, forge_command, java)
        return server_dir, forge_command, None

    memory = max(1, int(instance.memory_gb))
    main_jar = _resolve_main_jar(server_dir, instance)
    command = [
        java,
        f"-Xms{min(memory, 2)}G",
        f"-Xmx{memory}G",
        "-jar",
        main_jar,
        "nogui",
    ]
    _write_launch_record(server_dir, command, java)
    return server_dir, command, None


def _log_failure(server_dir: Path | None, message: str) -> None:
    print(f"MineBox launcher error: {message}", file=sys.stderr)
    if server_dir is None:
        return
    try:
        log_dir = server_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / "minebox-launcher.log"
        previous = ""
        if path.is_file():
            previous = path.read_text(encoding="utf-8", errors="ignore")
        path.write_text(previous + f"ERROR: {message}\n", encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    server_dir: Path | None = None
    try:
        server_dir, command, env = build_command()
        os.chdir(server_dir)
        # Do not steal Java stdout/stderr — Forge/Minecraft console logging
        # often goes there, and the dashboard reads logs/*.log for the UI.
        if env is None:
            os.execv(command[0], command)
        else:
            os.execve(command[0], command, env)
    except Exception as error:
        _log_failure(server_dir, str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
