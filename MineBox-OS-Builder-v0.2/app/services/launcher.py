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
    if parsed and parsed <= (1, 16, 5):
        return 8
    if parsed and parsed < (1, 20, 5):
        return 17
    return 21


def _java_candidates(version: str) -> list[str]:
    configured = os.environ.get("MINEBOX_JAVA")
    candidates: list[str] = [configured] if configured else []
    major = _required_java_major(version)

    if major <= 8:
        candidates.extend([
            "/usr/lib/jvm/java-8-openjdk-arm64/bin/java",
            "/usr/lib/jvm/java-8-openjdk-armhf/bin/java",
            "/usr/lib/jvm/java-8-openjdk-amd64/bin/java",
            "java8",
        ])
    elif major <= 17:
        candidates.extend([
            "/usr/lib/jvm/java-17-openjdk-arm64/bin/java",
            "/usr/lib/jvm/java-17-openjdk-amd64/bin/java",
            "/usr/lib/jvm/temurin-17-jdk-arm64/bin/java",
            "java17",
        ])
    else:
        candidates.extend([
            "/usr/lib/jvm/java-21-openjdk-arm64/bin/java",
            "/usr/lib/jvm/java-21-openjdk-amd64/bin/java",
            "/usr/lib/jvm/temurin-21-jdk-arm64/bin/java",
            "java21",
        ])

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


def _find_java(version: str) -> str:
    required = _required_java_major(version)
    fallback: str | None = None
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
            fallback = fallback or resolved
            continue
        if major >= required:
            return resolved
        fallback = fallback or resolved

    if fallback:
        major = _java_major_version(fallback)
        if major is not None and major < required:
            raise RuntimeError(
                f"Minecraft {version} needs Java {required}+, but found Java "
                f"{major} at {fallback}. Install openjdk-{required}-jre-headless."
            )
        return fallback

    raise RuntimeError(
        f"No compatible Java runtime was found for Minecraft {version} "
        f"(needs Java {_required_java_major(version)}+)."
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
        (server_dir / "libraries" / "net" / "minecraftforge" / "forge").glob(
            "*/unix_args.txt"
        )
    )
    if matches:
        return matches[-1]

    neoforge = sorted(
        (server_dir / "libraries" / "net" / "neoforged" / "neoforge").glob(
            "*/unix_args.txt"
        )
    )
    if neoforge:
        return neoforge[-1]
    return None


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
    looks_like_forge = (
        loader in {"forge", "neoforge"}
        or unix_args is not None
        or run_sh.is_file()
        or (server_dir / ".minebox-forge-args").is_file()
        or any(server_dir.glob("forge-*-shim.jar"))
    )
    if not looks_like_forge:
        return None

    _write_user_jvm_args(server_dir, instance.memory_gb)

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

    for pattern in ("forge-*-shim.jar", "forge-*.jar"):
        for path in sorted(server_dir.glob(pattern)):
            if "installer" in path.name:
                continue
            memory = max(1, int(instance.memory_gb))
            return [
                java,
                f"-Xms{min(memory, 2)}G",
                f"-Xmx{memory}G",
                "-jar",
                path.name,
                "nogui",
            ]

    if run_sh.is_file():
        # Last resort: synthesize a safe launcher that skips onlyCheckJava.
        safe = server_dir / "minebox-forge-run.sh"
        # Parse the unix_args reference from run.sh when possible.
        text = run_sh.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"@(\S*libraries/\S+/unix_args\.txt)", text)
        if match:
            args_rel = match.group(1)
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

    return None


def _resolve_main_jar(server_dir: Path, instance: servers.ServerInstance) -> str:
    configured = (instance.main_jar or "server.jar").strip()
    if configured.startswith("@"):
        candidate = server_dir / configured[1:]
        if candidate.is_file():
            return configured

    if configured and not configured.startswith("@") and (server_dir / configured).is_file():
        return configured

    for name in (
        "fabric-server-launch.jar",
        "server.jar",
    ):
        if (server_dir / name).is_file():
            return name

    for path in sorted(server_dir.glob("forge-*-shim.jar")):
        return path.name
    for path in sorted(server_dir.glob("forge-*.jar")):
        if "installer" in path.name:
            continue
        return path.name

    raise RuntimeError(
        f"The active server '{instance.name}' does not have a launchable server jar."
    )


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
        # Keep stderr in a file so dashboard start failures can show the real reason.
        log_dir = server_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stderr_path = log_dir / "minebox-stderr.log"
        stderr_fd = os.open(
            stderr_path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o644,
        )
        os.dup2(stderr_fd, 2)
        os.close(stderr_fd)
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
