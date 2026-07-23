from pathlib import Path

APP_VERSION = "1.4.0-os-preview"

SERVICE_NAME = "minecraft.service"

MINECRAFT_DIR = Path("/opt/minecraft")
SERVER_PROPERTIES = MINECRAFT_DIR / "server.properties"
SERVER_LOG = MINECRAFT_DIR / "logs/latest.log"
CRASH_REPORT_DIR = MINECRAFT_DIR / "crash-reports"
BACKUP_DIR = MINECRAFT_DIR / "backups"

MINEBOX_DATA_DIR = Path.home() / ".config/minebox"
SETTINGS_FILE = MINEBOX_DATA_DIR / "settings.json"
APP_LOG = MINEBOX_DATA_DIR / "minebox.log"

MCRCON_PATH = "/usr/local/bin/mcrcon"
RCON_HOST = "127.0.0.1"
RCON_PORT = "25575"
RCON_PASSWORD_FILE = MINECRAFT_DIR / ".minebox-rcon-password"
