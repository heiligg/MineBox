from __future__ import annotations

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


def _path_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _active_log_candidates() -> list[Path]:
    paths: list[Path] = []
    active = servers.active_server()
    if active is None:
        return paths

    logs_dir = Path(active.directory) / "logs"
    preferred = (
        "latest.log",
        "fml-server-latest.log",
        "debug.log",
        "minebox-stderr.log",
        "minebox-console.log",
    )
    for name in preferred:
        paths.append(logs_dir / name)

    if logs_dir.is_dir():
        try:
            extras = sorted(
                logs_dir.glob("*.log"),
                key=_path_mtime,
                reverse=True,
            )
        except OSError:
            extras = []
        for path in extras:
            if path not in paths:
                paths.append(path)
    return paths


def minecraft_log_path() -> Path | None:
    configured_path = os.environ.get("MINEBOX_MINECRAFT_LOG")

    if configured_path:
        path = Path(configured_path).expanduser()
        if _path_is_file(path) and _path_size(path) > 0:
            return path

    usable = [
        path
        for path in _active_log_candidates()
        if _path_is_file(path) and _path_size(path) > 0
    ]
    if usable:
        # Prefer the newest non-empty log so Forge FML / stderr captures work.
        usable.sort(key=lambda path: (_path_mtime(path), _path_size(path)), reverse=True)
        # Still prefer classic latest.log when it has real content.
        for path in usable:
            if path.name == "latest.log" and _path_size(path) > 64:
                return path
        return usable[0]

    for path in DEFAULT_LOG_PATHS:
        if _path_is_file(path) and _path_size(path) > 0:
            return path

    return None


def append_console_line(line: str) -> None:
    """Mirror dashboard/RCON activity into a log the console UI can show."""
    active = servers.active_server()
    if active is None:
        return
    path = Path(active.directory) / "logs" / "minebox-console.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line.rstrip("\n") + "\n")
    except OSError:
        pass


def _read_tail(path: Path, line_count: int) -> list[str]:
    with path.open("r", encoding="utf-8", errors="replace") as log_file:
        return [line.rstrip("\n") for line in log_file.readlines()[-line_count:]]


def latest_lines(line_count: int = 100) -> dict:
    line_count = max(1, min(line_count, 500))
    path = minecraft_log_path()

    if path is None:
        active = servers.active_server()
        expected = (
            str(Path(active.directory) / "logs" / "latest.log")
            if active is not None
            else None
        )
        return {
            "available": False,
            "path": expected,
            "lines": [],
            "message": (
                "Minecraft log is not available yet. Start the server and wait "
                "a few seconds for logs/latest.log to appear."
            ),
        }

    try:
        lines = _read_tail(path, line_count)

        # Merge recent MineBox console echoes when the primary log is a game log.
        active = servers.active_server()
        if active is not None and path.name != "minebox-console.log":
            mirror = Path(active.directory) / "logs" / "minebox-console.log"
            if _path_is_file(mirror) and _path_size(mirror) > 0:
                mirrored = _read_tail(mirror, min(40, line_count))
                if mirrored:
                    lines = (lines + mirrored)[-line_count:]

        return {
            "available": True,
            "path": str(path),
            "lines": lines,
            "message": None,
        }
    except OSError as error:
        return {
            "available": False,
            "path": str(path),
            "lines": [],
            "message": f"Unable to read Minecraft log: {error}",
        }
