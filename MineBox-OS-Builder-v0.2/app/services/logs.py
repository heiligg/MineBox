from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from config import SERVICE_NAME
from services import servers


DEFAULT_LOG_PATHS = (
    Path("/opt/minecraft/logs/latest.log"),
    Path("/opt/minecraft/server/logs/latest.log"),
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


def _active_logs_dir() -> Path | None:
    active = servers.active_server()
    if active is None:
        return None
    return Path(active.directory) / "logs"


def _file_candidates() -> list[Path]:
    paths: list[Path] = []
    logs_dir = _active_logs_dir()
    if logs_dir is not None:
        for name in (
            "latest.log",
            "fml-server-latest.log",
            "debug.log",
            "minebox-stderr.log",
            "minebox-console.log",
        ):
            paths.append(logs_dir / name)
        if logs_dir.is_dir():
            try:
                for path in sorted(
                    logs_dir.glob("*.log"),
                    key=_path_mtime,
                    reverse=True,
                ):
                    if path not in paths:
                        paths.append(path)
            except OSError:
                pass
    paths.extend(DEFAULT_LOG_PATHS)
    return paths


def minecraft_log_path() -> Path | None:
    configured_path = os.environ.get("MINEBOX_MINECRAFT_LOG")
    if configured_path:
        path = Path(configured_path).expanduser()
        if _path_is_file(path) and _path_size(path) > 0:
            return path

    usable = [
        path
        for path in _file_candidates()
        if _path_is_file(path) and _path_size(path) > 0
    ]
    if not usable:
        return None

    # Prefer a fresh latest.log; otherwise newest non-empty log.
    now = time.time()
    fresh_latest = [
        path
        for path in usable
        if path.name == "latest.log" and now - _path_mtime(path) < 120
    ]
    if fresh_latest:
        return fresh_latest[0]

    for path in usable:
        if path.name == "latest.log" and _path_size(path) > 0:
            return path

    usable.sort(key=_path_mtime, reverse=True)
    return usable[0]


def append_console_line(line: str) -> None:
    """Mirror dashboard/RCON activity into a log the console UI can show."""
    text = (line or "").rstrip("\n").strip()
    if not text or text == ">":
        return
    logs_dir = _active_logs_dir()
    if logs_dir is None:
        return
    path = logs_dir / "minebox-console.log"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")
    except OSError:
        pass


def _read_tail(path: Path, line_count: int) -> list[str]:
    with path.open("r", encoding="utf-8", errors="replace") as log_file:
        return [line.rstrip("\n") for line in log_file.readlines()[-line_count:]]


def _journal_lines(line_count: int) -> list[str]:
    """Live process output from minecraft.service (works when file logs stall)."""
    commands = [
        [
            "sudo",
            "-n",
            "/usr/bin/journalctl",
            "-u",
            SERVICE_NAME,
            "-n",
            str(line_count),
            "--no-pager",
            "-o",
            "cat",
        ],
        [
            "journalctl",
            "-u",
            SERVICE_NAME,
            "-n",
            str(line_count),
            "--no-pager",
            "-o",
            "cat",
        ],
    ]
    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        lines = [
            line.rstrip("\n")
            for line in (result.stdout or "").splitlines()
            if line.strip()
        ]
        if lines:
            return lines[-line_count:]
    return []


def _dedupe_preserve(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = line.strip()
        if not key:
            continue
        # Allow repeated chat/status lines; only drop exact consecutive dupes.
        if output and output[-1] == line:
            continue
        output.append(line)
        seen.add(key)
    return output


def latest_lines(line_count: int = 100) -> dict:
    line_count = max(1, min(line_count, 500))
    path = minecraft_log_path()
    file_lines: list[str] = []
    file_error: str | None = None

    if path is not None:
        try:
            file_lines = _read_tail(path, line_count)
        except OSError as error:
            file_error = str(error)

    journal_lines = _journal_lines(line_count)

    # If the on-disk log looks stale (common after Forge restarts), prefer journal.
    use_journal = False
    if journal_lines:
        if not file_lines:
            use_journal = True
        elif path is not None and time.time() - _path_mtime(path) > 45:
            use_journal = True
        elif file_lines and any(
            "Stopping server" in line or "Saving worlds" in line
            for line in file_lines[-8:]
        ):
            # File ends on a shutdown while journal may have the new boot.
            if any(
                "Starting minecraft server" in line
                or "Done (" in line
                or "Forged mod loading" in line
                or "MinecraftForge" in line
                for line in journal_lines[-40:]
            ):
                use_journal = True

    mirror_lines: list[str] = []
    logs_dir = _active_logs_dir()
    if logs_dir is not None:
        mirror = logs_dir / "minebox-console.log"
        if _path_is_file(mirror) and _path_size(mirror) > 0:
            try:
                mirror_lines = _read_tail(mirror, min(50, line_count))
            except OSError:
                mirror_lines = []

    if use_journal:
        lines = _dedupe_preserve(journal_lines + mirror_lines)[-line_count:]
        return {
            "available": True,
            "path": f"journal:{SERVICE_NAME}",
            "lines": lines,
            "message": None,
            "source": "journal",
        }

    if file_lines or mirror_lines:
        lines = _dedupe_preserve(file_lines + mirror_lines)[-line_count:]
        return {
            "available": True,
            "path": str(path) if path is not None else None,
            "lines": lines,
            "message": None,
            "source": "file",
        }

    if journal_lines:
        return {
            "available": True,
            "path": f"journal:{SERVICE_NAME}",
            "lines": journal_lines[-line_count:],
            "message": None,
            "source": "journal",
        }

    expected = str((_active_logs_dir() or Path("/opt/minecraft")) / "latest.log")
    return {
        "available": False,
        "path": expected,
        "lines": [],
        "message": file_error
        or (
            "Minecraft log is not available yet. Start the server and wait a "
            "few seconds, then refresh."
        ),
        "source": None,
    }
