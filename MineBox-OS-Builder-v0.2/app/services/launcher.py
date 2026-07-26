from __future__ import annotations

import os
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


def _resolve_main_jar(server_dir: Path, instance: servers.ServerInstance) -> str:
    configured = (instance.main_jar or "server.jar").strip()
    if configured.startswith("@"):
        return configured
    if configured and (server_dir / configured).is_file():
        return configured

    forge_args = server_dir / ".minebox-forge-args"
    if forge_args.is_file():
        relative = forge_args.read_text(encoding="utf-8").strip()
        if relative and (server_dir / relative).is_file():
            return f"@{relative}"

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


def build_command() -> tuple[Path, list[str]]:
    instance = servers.active_server()
    if instance is None:
        raise RuntimeError("No active Minecraft server is selected.")

    server_dir = Path(instance.directory)
    memory = max(1, int(instance.memory_gb))
    java = _find_java(instance.version)
    main_jar = _resolve_main_jar(server_dir, instance)

    command = [java, f"-Xms{memory}G", f"-Xmx{memory}G"]
    if main_jar.startswith("@"):
        # Modern Forge/NeoForge style argfiles.
        command.append(main_jar)
        command.append("nogui")
    else:
        command.extend(["-jar", main_jar, "nogui"])

    return server_dir, command


def main() -> int:
    try:
        server_dir, command = build_command()
        os.chdir(server_dir)
        os.execv(command[0], command)
    except Exception as error:
        print(f"MineBox launcher error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
