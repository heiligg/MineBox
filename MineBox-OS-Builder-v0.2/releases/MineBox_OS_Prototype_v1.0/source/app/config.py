"""Legacy compatibility exports.

Prefer `core.minebox_config.get_config()` and `core.secrets_store` for new code.
`RCON_PASSWORD` is no longer a hard-coded production constant.
"""

from __future__ import annotations

from pathlib import Path

try:
    from core.version import get_version as _get_version

    APP_VERSION = _get_version()
except Exception:  # noqa: BLE001
    # Direct file fallback when core is unavailable during early bootstrap.
    _ver = Path(__file__).resolve().parent / "VERSION"
    APP_VERSION = (
        _ver.read_text(encoding="utf-8").strip().splitlines()[0]
        if _ver.is_file()
        else "1.0.0-prototype.1"
    )
SERVICE_NAME = "minecraft.service"
MINECRAFT_DIR = Path("/opt/minecraft/server")
SERVER_PROPERTIES = MINECRAFT_DIR / "server.properties"
SERVER_LOG = MINECRAFT_DIR / "logs/latest.log"
CRASH_REPORT_DIR = MINECRAFT_DIR / "crash-reports"
BACKUP_DIR = Path("/opt/minecraft/backups")
MINEBOX_DATA_DIR = Path.home() / ".config/minebox"
SETTINGS_FILE = MINEBOX_DATA_DIR / "settings.json"
APP_LOG = MINEBOX_DATA_DIR / "minebox.log"
MCRCON_PATH = "/usr/local/bin/mcrcon"
RCON_HOST = "127.0.0.1"
RCON_PORT = "25575"


def get_rcon_password() -> str:
    """Return a generated/migrated RCON secret — never a shipped universal default."""
    from core.secrets_store import get_rcon_password as _get

    return _get()


def __getattr__(name: str):
    if name == "RCON_PASSWORD":
        return get_rcon_password()
    raise AttributeError(f"module 'config' has no attribute {name!r}")
