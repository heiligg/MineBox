"""Network recovery helpers with restart-loop protection."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("minebox.network.recovery")

MAX_BURST = 5
WINDOW_S = 300


def _runtime_dir() -> Path:
    return Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox"))


def recovery_state_path() -> Path:
    return _runtime_dir() / "network_recovery.json"


def _load() -> dict[str, Any]:
    path = recovery_state_path()
    if not path.is_file():
        return {"attempts": [], "last_error": None, "progress": "idle"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {"attempts": [], "last_error": None, "progress": "idle"}


def _save(data: dict[str, Any]) -> None:
    path = recovery_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def can_attempt(action: str) -> tuple[bool, float]:
    """Return (allowed, retry_after_seconds)."""
    data = _load()
    now = time.time()
    attempts = [float(t) for t in data.get("attempts") or [] if now - float(t) < WINDOW_S]
    data["attempts"] = attempts
    _save(data)
    if len(attempts) >= MAX_BURST:
        oldest = min(attempts) if attempts else now
        return False, max(1.0, WINDOW_S - (now - oldest))
    return True, 0.0


def record_attempt(action: str, *, error: str | None = None, progress: str = "running") -> None:
    data = _load()
    attempts = [float(t) for t in data.get("attempts") or []]
    attempts.append(time.time())
    data["attempts"] = attempts[-MAX_BURST:]
    data["last_action"] = action
    data["last_error"] = error
    data["progress"] = progress
    data["updated_at"] = time.time()
    _save(data)
    if error:
        LOGGER.warning("network_recovery action=%s error=%s", action, error)
    else:
        LOGGER.info("network_recovery action=%s progress=%s", action, progress)


def mark_progress(progress: str, *, error: str | None = None) -> None:
    data = _load()
    data["progress"] = progress
    if error is not None:
        data["last_error"] = error
    data["updated_at"] = time.time()
    _save(data)


def status() -> dict[str, Any]:
    data = _load()
    allowed, retry = can_attempt("status-check")
    # can_attempt for status-check shouldn't consume — reload without adding
    data = _load()
    now = time.time()
    attempts = [float(t) for t in data.get("attempts") or [] if now - float(t) < WINDOW_S]
    return {
        "progress": data.get("progress") or "idle",
        "last_error": data.get("last_error"),
        "last_action": data.get("last_action"),
        "attempts_in_window": len(attempts),
        "max_burst": MAX_BURST,
        "window_s": WINDOW_S,
        "restart_limited": len(attempts) >= MAX_BURST,
        "retry_after_s": retry if len(attempts) >= MAX_BURST else 0,
    }


def manual_retry(action: str = "manual_retry") -> dict[str, Any]:
    allowed, retry = can_attempt(action)
    if not allowed:
        return {
            "ok": False,
            "detail": f"Recovery restart limit reached. Retry in {int(retry)}s.",
            "retry_after_s": retry,
            **status(),
        }
    record_attempt(action, progress="manual_retry")
    return {"ok": True, "detail": "Manual recovery recorded.", **status()}
