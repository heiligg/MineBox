"""Local-display trust: loopback-only token for scoped appliance actions."""

from __future__ import annotations

import ipaddress
import os
import secrets
from pathlib import Path
from typing import Any

DISPLAY_TOKEN_HEADER = "X-MineBox-Display-Token"
DISPLAY_COOKIE = "minebox_display"


def _runtime_dir() -> Path:
    return Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox"))


def token_path() -> Path:
    override = os.environ.get("MINEBOX_DISPLAY_TOKEN_FILE")
    if override:
        return Path(override)
    return _runtime_dir() / "display_token"


def ensure_display_token() -> str:
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        token = path.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
    token = secrets.token_urlsafe(32)
    path.write_text(token + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return token


def read_display_token() -> str | None:
    path = token_path()
    if not path.is_file():
        return None
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token if len(token) >= 32 else None


def verify_display_token(provided: str | None) -> bool:
    if not provided:
        return False
    expected = read_display_token() or ensure_display_token()
    return secrets.compare_digest(expected, provided.strip())


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    value = host.split("%")[0].strip("[]")
    if value in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def client_is_loopback(client_host: str | None) -> bool:
    return is_loopback_host(client_host)


ALLOWED_ACTION_SCOPES = frozenset(
    {
        "server_start",
        "server_stop",
        "server_restart",
        "backup_create",
        "services_restart",
        "device_reboot",
        "device_shutdown",
    }
)


def public_trust_info() -> dict[str, Any]:
    return {
        "model": "loopback_display_token",
        "header": DISPLAY_TOKEN_HEADER,
        "cookie": DISPLAY_COOKIE,
        "remote_reuse": False,
        "requires_loopback": True,
        "scopes": sorted(ALLOWED_ACTION_SCOPES),
        "notes": (
            "Display actions accept a file-backed token only from loopback. "
            "The administrator password is never embedded. "
            "Remote clients cannot reuse the display token."
        ),
    }
