from __future__ import annotations

import os
from pathlib import Path

APP_VERSION = "0.2.0"
SERVICE_NAME = "minecraft.service"

MINECRAFT_ROOT = Path("/opt/minecraft")
SERVERS_DIR = MINECRAFT_ROOT / "servers"
METADATA_DIR = MINECRAFT_ROOT / "metadata"
ACTIVE_SERVER_FILE = METADATA_DIR / "active_server"


def active_server_id() -> str | None:
    try:
        value = ACTIVE_SERVER_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def active_server_directory() -> Path:
    server_id = active_server_id()
    if not server_id:
        return MINECRAFT_ROOT
    return SERVERS_DIR / server_id


class ActiveServerPath(os.PathLike[str]):
    """A path that resolves against the selected MineBox server on each use."""

    def __init__(self, relative: str = "") -> None:
        self.relative = relative

    def resolve_path(self) -> Path:
        base = active_server_directory()
        return base / self.relative if self.relative else base

    def __fspath__(self) -> str:
        return str(self.resolve_path())

    def __str__(self) -> str:
        return str(self.resolve_path())

    def __truediv__(self, other: object) -> "ActiveServerPath":
        relative = Path(self.relative) / str(other)
        return ActiveServerPath(str(relative))

    def __getattr__(self, name: str):
        return getattr(self.resolve_path(), name)


MINECRAFT_DIR = ActiveServerPath()
SERVER_PROPERTIES = ActiveServerPath("server.properties")
SERVER_LOG = ActiveServerPath("logs/latest.log")
CRASH_REPORT_DIR = ActiveServerPath("crash-reports")


def active_backup_directory() -> Path:
    server_id = active_server_id() or "legacy"
    return MINECRAFT_ROOT / "backups" / server_id


class ActiveBackupPath(os.PathLike[str]):
    def resolve_path(self) -> Path:
        return active_backup_directory()

    def __fspath__(self) -> str:
        return str(self.resolve_path())

    def __str__(self) -> str:
        return str(self.resolve_path())

    def __truediv__(self, other: object) -> Path:
        return self.resolve_path() / str(other)

    def __getattr__(self, name: str):
        return getattr(self.resolve_path(), name)


BACKUP_DIR = ActiveBackupPath()

MINEBOX_DATA_DIR = Path.home() / ".config/minebox"
SETTINGS_FILE = MINEBOX_DATA_DIR / "settings.json"
APP_LOG = MINEBOX_DATA_DIR / "minebox.log"

MCRCON_PATH = "/usr/local/bin/mcrcon"
RCON_HOST = "127.0.0.1"
RCON_PORT = "25575"
RCON_PASSWORD_FILE = ActiveServerPath(".minebox-rcon-password")
