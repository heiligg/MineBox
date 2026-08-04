"""Simple file-backed rate limiter for appliance auth/control endpoints."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any


_LOCK = threading.Lock()


def _path() -> Path:
    root = Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox"))
    return root / "rate_limits.json"


def _load() -> dict[str, Any]:
    path = _path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, Any]) -> None:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def check_rate_limit(
    key: str,
    *,
    max_attempts: int,
    window_s: float,
    cooldown_s: float | None = None,
) -> tuple[bool, float]:
    """Return (allowed, retry_after_seconds).

    On failure paths callers should call ``record_failure``.
    Successful auth should call ``clear``.
    """
    cooldown_s = float(cooldown_s if cooldown_s is not None else window_s)
    now = time.time()
    with _LOCK:
        data = _load()
        entry = data.get(key) or {}
        locked_until = float(entry.get("locked_until") or 0)
        if locked_until > now:
            return False, locked_until - now
        attempts = [
            float(ts)
            for ts in (entry.get("attempts") or [])
            if now - float(ts) <= window_s
        ]
        entry["attempts"] = attempts
        data[key] = entry
        _save(data)
        if len(attempts) >= max_attempts:
            entry["locked_until"] = now + cooldown_s
            data[key] = entry
            _save(data)
            return False, cooldown_s
        return True, 0.0


def record_failure(key: str) -> None:
    now = time.time()
    with _LOCK:
        data = _load()
        entry = data.get(key) or {"attempts": []}
        attempts = list(entry.get("attempts") or [])
        attempts.append(now)
        entry["attempts"] = attempts[-50:]
        data[key] = entry
        _save(data)


def clear(key: str) -> None:
    with _LOCK:
        data = _load()
        if key in data:
            del data[key]
            _save(data)


def client_key(request, suffix: str) -> str:
    host = "unknown"
    try:
        if request.client and request.client.host:
            host = request.client.host
    except Exception:
        pass
    # Prefer X-Forwarded-For only from localhost reverse proxies (not trusted by default).
    return f"{suffix}:{host}"
