from __future__ import annotations
import json
from config import MINEBOX_DATA_DIR, SETTINGS_FILE

DEFAULTS = {
    "refresh_seconds": 2,
    "temperature_unit": "C",
    "screen_timeout_minutes": 0,
    "brightness": 100,
    "theme": "classic",
    "backup_retention": 10,
    "confirm_server_actions": True,
    "automatic_backup_hours": 0,
    "scheduled_restart_time": "",
    "dashboard_quick_actions": False,
}

def load() -> dict:
    MINEBOX_DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = dict(DEFAULTS)
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            data.update(saved)
    except (OSError, ValueError, TypeError):
        pass
    return data

def save(settings: dict) -> tuple[bool, str]:
    try:
        MINEBOX_DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        return True, "Settings saved."
    except OSError as exc:
        return False, str(exc)
