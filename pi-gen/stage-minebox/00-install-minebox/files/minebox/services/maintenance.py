from __future__ import annotations

import json
import time
from pathlib import Path

from config import MINEBOX_DATA_DIR
from services import backups, minecraft, settings

STATE_FILE = MINEBOX_DATA_DIR / 'maintenance-state.json'


def _state() -> dict:
    try:
        value = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(value: dict) -> None:
    MINEBOX_DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def run_once(now: float | None = None) -> list[str]:
    now = time.time() if now is None else now
    cfg = settings.load(); state = _state(); messages: list[str] = []
    interval = max(0, int(cfg.get('automatic_backup_hours', 0)))
    if interval:
        last = float(state.get('last_auto_backup', 0))
        if now - last >= interval * 3600:
            result = backups.create()
            messages.append(result.message)
            if result.ok: state['last_auto_backup'] = now
    restart_time = str(cfg.get('scheduled_restart_time', '')).strip()
    if restart_time and len(restart_time) == 5:
        current = time.strftime('%H:%M', time.localtime(now))
        today = time.strftime('%Y-%m-%d', time.localtime(now))
        if current == restart_time and state.get('last_restart_date') != today:
            result = minecraft.restart()
            messages.append(result.message)
            if result.ok: state['last_restart_date'] = today
    _save_state(state)
    return messages
