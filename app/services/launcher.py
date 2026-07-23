from __future__ import annotations

import os
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


def build_command() -> tuple[Path, list[str]]:
    instance = servers.active_server()
    if instance is None:
        raise RuntimeError("No active Minecraft server is selected.")

    server_dir = Path(instance.directory)
    server_jar = server_dir / "server.jar"
    if not server_jar.is_file():
        raise RuntimeError(
            f"The active server '{instance.name}' does not have server.jar."
        )

    memory = max(1, int(instance.memory_gb))
    java = _find_java(instance.version)
    command = [
        java,
        f"-Xms{memory}G",
        f"-Xmx{memory}G",
        "-jar",
        "server.jar",
        "nogui",
    ]
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
