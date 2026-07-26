from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
from pathlib import Path
from typing import Any


DEFAULT_AUTH_FILE = Path("/var/lib/minebox/auth.json")
LEGACY_AUTH_FILES = (
    Path("/opt/minebox/config/auth.json"),
    Path("/opt/minebox.previous/config/auth.json"),
    Path("/opt/minebox/auth.json"),
    Path("/opt/minebox.previous/auth.json"),
)

AUTH_FILE = Path(
    os.environ.get(
        "MINEBOX_AUTH_FILE",
        str(DEFAULT_AUTH_FILE),
    )
).expanduser()

DEFAULT_USERNAME = "admin"

TRIVIAL_PASSWORDS = {
    "minebox",
    "minecraft",
    "password",
    "password1",
    "password123",
    "admin",
    "admin123",
    "12345678",
    "123456789012",
    "letmein",
    "changeme",
    "raspberry",
    "pi",
}


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError(
            "Password must contain at least 12 characters."
        )
    if len(password) > 200:
        raise ValueError("Password is too long.")
    normalized = password.lower().strip()
    if normalized in TRIVIAL_PASSWORDS or normalized.startswith("minebox"):
        raise ValueError(
            "Choose a stronger password (not a common default like minebox/password)."
        )


def _ensure_parent_directory() -> None:
    AUTH_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        AUTH_FILE.parent.chmod(0o700)
    except OSError:
        pass


def _migrate_legacy_auth() -> None:
    """
    Keep admin credentials across OTA updates.

    Older builds stored auth.json under /opt/minebox, which is replaced on
    every update. Migrate once into /var/lib/minebox.
    """

    if AUTH_FILE.exists():
        return

    for legacy in LEGACY_AUTH_FILES:
        if not legacy.is_file():
            continue
        try:
            _ensure_parent_directory()
            shutil.copy2(legacy, AUTH_FILE)
            try:
                AUTH_FILE.chmod(0o600)
            except OSError:
                pass
            return
        except OSError:
            continue


def _load() -> dict[str, Any]:
    _migrate_legacy_auth()

    if not AUTH_FILE.exists():
        return {}

    try:
        data = json.loads(
            AUTH_FILE.read_text(encoding="utf-8")
        )
    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
    ):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def _save(data: dict[str, Any]) -> None:
    _ensure_parent_directory()

    temporary_file = AUTH_FILE.with_suffix(".tmp")

    temporary_file.write_text(
        json.dumps(
            data,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    temporary_file.chmod(0o600)
    temporary_file.replace(AUTH_FILE)

    try:
        AUTH_FILE.chmod(0o600)
    except OSError:
        pass

    # Keep a compatibility copy for older tooling, but /var/lib is authoritative.
    if AUTH_FILE.resolve() != Path("/opt/minebox/config/auth.json").resolve():
        try:
            legacy = Path("/opt/minebox/config/auth.json")
            legacy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(AUTH_FILE, legacy)
            legacy.chmod(0o600)
        except OSError:
            pass


def is_configured() -> bool:
    data = _load()

    required = {
        "username",
        "password_hash",
        "password_salt",
        "session_secret",
    }

    return required.issubset(data)


def get_username() -> str:
    data = _load()
    username = data.get("username")

    if isinstance(username, str) and username:
        return username

    return DEFAULT_USERNAME


def get_session_secret() -> str:
    data = _load()
    existing = data.get("session_secret")

    if isinstance(existing, str) and len(existing) >= 32:
        return existing

    generated = secrets.token_urlsafe(48)

    data["session_secret"] = generated
    _save(data)

    return generated


def _derive_password_hash(
    password: str,
    salt: bytes,
) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=64,
    )


def create_admin(
    username: str,
    password: str,
) -> None:
    username = username.strip()

    if not username:
        raise ValueError("Username cannot be empty.")

    if len(username) > 64:
        raise ValueError(
            "Username cannot be longer than 64 characters."
        )

    validate_password(password)

    data = _load()

    if is_configured():
        raise ValueError(
            "MineBox authentication is already configured."
        )

    salt = secrets.token_bytes(32)
    password_hash = _derive_password_hash(
        password,
        salt,
    )

    data.update(
        {
            "username": username,
            "password_salt": salt.hex(),
            "password_hash": password_hash.hex(),
            "session_secret": data.get(
                "session_secret",
                secrets.token_urlsafe(48),
            ),
        }
    )

    _save(data)


def verify_credentials(
    username: str,
    password: str,
) -> bool:
    data = _load()

    stored_username = data.get("username")
    salt_hex = data.get("password_salt")
    hash_hex = data.get("password_hash")

    if not all(
        isinstance(value, str)
        for value in (
            stored_username,
            salt_hex,
            hash_hex,
        )
    ):
        return False

    if not hmac.compare_digest(
        username.strip(),
        stored_username,
    ):
        return False

    try:
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)
    except ValueError:
        return False

    supplied_hash = _derive_password_hash(
        password,
        salt,
    )

    return hmac.compare_digest(
        supplied_hash,
        expected_hash,
    )


def change_password(
    current_password: str,
    new_password: str,
) -> None:
    data = _load()
    username = get_username()
    if not verify_credentials(username, current_password):
        raise ValueError("Current password is incorrect.")
    validate_password(new_password)
    if hmac.compare_digest(current_password, new_password):
        raise ValueError("New password must be different from the current password.")

    salt = secrets.token_bytes(32)
    password_hash = _derive_password_hash(new_password, salt)
    data["password_salt"] = salt.hex()
    data["password_hash"] = password_hash.hex()
    data["password_changed_at"] = (
        __import__("datetime")
        .datetime.now(__import__("datetime").timezone.utc)
        .isoformat()
    )
    _save(data)


def security_reminder_status() -> dict[str, Any]:
    data = _load()
    dismissed = bool(data.get("security_reminder_dismissed"))
    return {
        "dismissed": dismissed,
        "show_reminder": not dismissed,
        "message": (
            "Change the MineBox admin password and the Linux/SSH "
            "`minebox` user password before exposing this device on a network."
        ),
    }


def dismiss_security_reminder() -> None:
    data = _load()
    data["security_reminder_dismissed"] = True
    _save(data)
