from __future__ import annotations

import os
import re
import shutil
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


def _java_candidates(version: str) -> list[str]:
    configured = os.environ.get("MINEBOX_JAVA")
    candidates: list[str] = [configured] if configured else []
    parsed = _version_tuple(version)

    if parsed and parsed <= (1, 16, 5):
        candidates.extend([
            "/usr/lib/jvm/java-8-openjdk-arm64/bin/java",
            "/usr/lib/jvm/java-8-openjdk-armhf/bin/java",
            "/usr/lib/jvm/java-8-openjdk-amd64/bin/java",
            "java8",
        ])
    elif parsed and parsed < (1, 20, 5):
        candidates.extend([
            "/usr/lib/jvm/java-17-openjdk-arm64/bin/java",
            "/usr/lib/jvm/java-17-openjdk-amd64/bin/java",
            "java17",
        ])
    else:
        candidates.extend([
            "/usr/lib/jvm/java-21-openjdk-arm64/bin/java",
            "/usr/lib/jvm/java-21-openjdk-amd64/bin/java",
            "java21",
        ])

    candidates.append("java")
    return candidates


def _find_java(version: str) -> str:
    for candidate in _java_candidates(version):
        if not candidate:
            continue
        if "/" in candidate:
            path = Path(candidate)
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
        else:
            found = shutil.which(candidate)
            if found:
                return found
    raise RuntimeError(
        f"No compatible Java runtime was found for Minecraft {version}."
    )


def _write_user_jvm_args(server_dir: Path, memory_gb: int) -> Path:
    """Keep Forge/NeoForge memory settings in the official JVM argfile."""
    path = server_dir / "user_jvm_args.txt"
    memory = max(1, int(memory_gb))
    memory_lines = [f"-Xms{memory}G", f"-Xmx{memory}G"]

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

    # Preserve comments/blank structure, then ensure memory args exist.
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
    )
    if not looks_like_forge:
        return None

    _write_user_jvm_args(server_dir, instance.memory_gb)

    # Official installer script is the most reliable launch path.
    if run_sh.is_file():
        return ["/bin/bash", str(run_sh), "nogui"]

    if unix_args is None:
        return None

    user_jvm = server_dir / "user_jvm_args.txt"
    return [
        java,
        f"@{user_jvm.resolve()}",
        f"@{unix_args.resolve()}",
        "nogui",
    ]


def _resolve_main_jar(server_dir: Path, instance: servers.ServerInstance) -> str:
    configured = (instance.main_jar or "server.jar").strip()
    if configured.startswith("@"):
        # Handled by _forge_command; fall through only if missing.
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

    java = _find_java(instance.version)
    forge_command = _forge_command(server_dir, instance, java)
    if forge_command is not None:
        java_bin = Path(java).resolve()
        env = os.environ.copy()
        # Ensure Forge run.sh's bare `java` calls use the right runtime.
        if java_bin.parent.name == "bin":
            env["JAVA_HOME"] = str(java_bin.parent.parent)
        env["PATH"] = f"{java_bin.parent}{os.pathsep}{env.get('PATH', '')}"
        return server_dir, forge_command, env

    memory = max(1, int(instance.memory_gb))
    main_jar = _resolve_main_jar(server_dir, instance)
    command = [java, f"-Xms{memory}G", f"-Xmx{memory}G", "-jar", main_jar, "nogui"]
    return server_dir, command, None


def _log_failure(server_dir: Path | None, message: str) -> None:
    print(f"MineBox launcher error: {message}", file=sys.stderr)
    if server_dir is None:
        return
    try:
        log_dir = server_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "minebox-launcher.log").write_text(
            message + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def main() -> int:
    server_dir: Path | None = None
    try:
        server_dir, command, env = build_command()
        os.chdir(server_dir)
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
