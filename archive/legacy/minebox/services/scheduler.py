from __future__ import annotations
import json
from config import SCHEDULE_FILE

DEFAULT = {"enabled": False, "interval_hours": 6, "keep_count": 12}

def load() -> dict:
    try:
        data = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
        return {**DEFAULT, **data}
    except (OSError, ValueError, TypeError):
        return dict(DEFAULT)

def save(data: dict) -> tuple[bool, str]:
    try:
        SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCHEDULE_FILE.write_text(json.dumps({**DEFAULT, **data}, indent=2) + "\n", encoding="utf-8")
        return True, "Backup schedule saved."
    except OSError as exc:
        return False, str(exc)
