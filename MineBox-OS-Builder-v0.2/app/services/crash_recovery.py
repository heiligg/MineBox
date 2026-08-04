"""Crash history and conservative automatic recovery policy."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _runtime_dir() -> Path:
    return Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox"))


def _path() -> Path:
    return _runtime_dir() / "crash_history.json"


def _load() -> dict[str, Any]:
    path = _path()
    if not path.is_file():
        return {
            "auto_restart": False,
            "max_attempts": 3,
            "cooldown_s": 120,
            "attempts": 0,
            "last_failure_at": None,
            "last_failure_reason": None,
            "events": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "auto_restart": False,
            "max_attempts": 3,
            "cooldown_s": 120,
            "attempts": 0,
            "last_failure_at": None,
            "last_failure_reason": None,
            "events": [],
        }
    if not isinstance(data, dict):
        return {
            "auto_restart": False,
            "max_attempts": 3,
            "cooldown_s": 120,
            "attempts": 0,
            "last_failure_at": None,
            "last_failure_reason": None,
            "events": [],
        }
    return data


def _save(data: dict[str, Any]) -> None:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def record_failure(reason: str) -> dict[str, Any]:
    from core.secrets_store import redact_secrets

    data = _load()
    now = time.time()
    last = float(data.get("last_failure_at") or 0)
    cooldown = float(data.get("cooldown_s") or 120)
    if last and (now - last) > cooldown * 3:
        # Long quiet period resets the loop counter.
        data["attempts"] = 0
    data["attempts"] = int(data.get("attempts") or 0) + 1
    data["last_failure_at"] = now
    data["last_failure_reason"] = redact_secrets(reason)[:500]
    events = list(data.get("events") or [])
    events.append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "reason": data["last_failure_reason"],
            "attempt": data["attempts"],
        }
    )
    data["events"] = events[-50:]
    _save(data)
    return status()


def reset_attempts() -> None:
    data = _load()
    data["attempts"] = 0
    _save(data)


def should_auto_restart() -> tuple[bool, str]:
    data = _load()
    if not data.get("auto_restart"):
        return False, "Automatic restart is disabled (conservative default)."
    attempts = int(data.get("attempts") or 0)
    max_attempts = int(data.get("max_attempts") or 3)
    if attempts >= max_attempts:
        return False, f"Crash-loop protection: {attempts}/{max_attempts} attempts exhausted."
    last = float(data.get("last_failure_at") or 0)
    cooldown = float(data.get("cooldown_s") or 120)
    if last and (time.time() - last) < cooldown:
        remaining = int(cooldown - (time.time() - last))
        return False, f"Cooldowning down ({remaining}s remaining)."
    return True, "Auto-restart allowed."


def status() -> dict[str, Any]:
    data = _load()
    allowed, reason = should_auto_restart()
    return {
        "auto_restart": bool(data.get("auto_restart")),
        "max_attempts": int(data.get("max_attempts") or 3),
        "cooldown_s": int(data.get("cooldown_s") or 120),
        "attempts": int(data.get("attempts") or 0),
        "last_failure_at": data.get("last_failure_at"),
        "last_failure_reason": data.get("last_failure_reason"),
        "auto_restart_allowed_now": allowed,
        "auto_restart_reason": reason,
        "events": list(data.get("events") or [])[-10:],
    }


def configure(
    *,
    auto_restart: bool | None = None,
    max_attempts: int | None = None,
    cooldown_s: int | None = None,
) -> dict[str, Any]:
    data = _load()
    if auto_restart is not None:
        data["auto_restart"] = bool(auto_restart)
    if max_attempts is not None:
        data["max_attempts"] = max(1, min(20, int(max_attempts)))
    if cooldown_s is not None:
        data["cooldown_s"] = max(10, min(3600, int(cooldown_s)))
    _save(data)
    return status()
