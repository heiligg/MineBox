import os
from pathlib import Path

from services import servers


DEFAULT_LOG_PATHS = (
    Path("/opt/minecraft/logs/latest.log"),
    Path("/opt/minecraft/server/logs/latest.log"),
    Path("/srv/minecraft/logs/latest.log"),
    Path("/home/minecraft/server/logs/latest.log"),
    Path("/var/lib/minecraft/logs/latest.log"),
)


def _path_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def minecraft_log_path() -> Path | None:
    configured_path = os.environ.get("MINEBOX_MINECRAFT_LOG")

    if configured_path:
        path = Path(configured_path).expanduser()
        if _path_is_file(path):
            return path

    active = servers.active_server()
    if active is not None:
        active_log = Path(active.directory) / "logs" / "latest.log"
        if _path_is_file(active_log):
            return active_log

    for path in DEFAULT_LOG_PATHS:
        if _path_is_file(path):
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
