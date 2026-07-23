import os
from pathlib import Path


DEFAULT_LOG_PATHS = (
    Path("/opt/minecraft/logs/latest.log"),
    Path("/srv/minecraft/logs/latest.log"),
    Path("/home/minecraft/server/logs/latest.log"),
    Path("/var/lib/minecraft/logs/latest.log"),
)


def minecraft_log_path() -> Path | None:
    configured_path = os.environ.get("MINEBOX_MINECRAFT_LOG")

    if configured_path:
        path = Path(configured_path).expanduser()

        if path.is_file():
            return path

    for path in DEFAULT_LOG_PATHS:
        if path.is_file():
            return path

    return None


def latest_lines(line_count: int = 100) -> dict:
    line_count = max(1, min(line_count, 500))
    path = minecraft_log_path()

    if path is None:
        return {
            "available": False,
            "path": None,
            "lines": [],
            "message": "Minecraft log is not available on this system.",
        }

    try:
        with path.open(
            "r",
            encoding="utf-8",
            errors="replace",
        ) as log_file:
            lines = log_file.readlines()[-line_count:]

        return {
            "available": True,
            "path": str(path),
            "lines": [line.rstrip("\n") for line in lines],
            "message": None,
        }
    except OSError as error:
        return {
            "available": False,
            "path": str(path),
            "lines": [],
            "message": f"Unable to read Minecraft log: {error}",
        }
