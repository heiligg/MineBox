from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any


AUTH_FILE = Path(
    os.environ.get(
        "MINEBOX_AUTH_FILE",
        "/opt/minebox/config/auth.json",
    )
)

DEFAULT_USERNAME = "admin"


def _ensure_parent_directory() -> None:
    AUTH_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        AUTH_FILE.parent.chmod(0o700)
    except OSError:
        pass


def _load() -> dict[str, Any]:
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

    if len(password) < 8:
        raise ValueError(
            "Password must contain at least 8 characters."
        )

    if len(password) > 200:
        raise ValueError("Password is too long.")

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
