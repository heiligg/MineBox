from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("minebox.auth")

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
ALGO_ARGON2ID = "argon2id"
ALGO_SCRYPT = "scrypt"

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
        raise ValueError("Password must contain at least 12 characters.")
    if len(password) > 200:
        raise ValueError("Password is too long.")
    normalized = password.lower().strip()
    if normalized in TRIVIAL_PASSWORDS or normalized.startswith("minebox"):
        raise ValueError(
            "Choose a stronger password (not a common default like minebox/password)."
        )


def _ensure_parent_directory() -> None:
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        AUTH_FILE.parent.chmod(0o700)
    except OSError:
        pass


def _migrate_legacy_auth() -> None:
    if AUTH_FILE.exists():
        return
    # Tests/dev with an explicit auth file must not pull image credentials.
    if os.environ.get("MINEBOX_AUTH_FILE"):
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
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, Any]) -> None:
    _ensure_parent_directory()
    temporary_file = AUTH_FILE.with_suffix(".tmp")
    temporary_file.write_text(
        json.dumps(data, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_file.chmod(0o600)
    temporary_file.replace(AUTH_FILE)
    try:
        AUTH_FILE.chmod(0o600)
    except OSError:
        pass
    # Never mirror into image paths when tests/dev override AUTH_FILE.
    if os.environ.get("MINEBOX_AUTH_FILE"):
        return
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
    if not isinstance(data.get("username"), str):
        return False
    if not isinstance(data.get("password_hash"), str) or not data.get("password_hash"):
        return False
    if not isinstance(data.get("session_secret"), str) or len(data["session_secret"]) < 32:
        return False
    algo = data.get("password_algo", ALGO_SCRYPT)
    if algo == ALGO_ARGON2ID:
        return True
    return isinstance(data.get("password_salt"), str) and bool(data.get("password_salt"))


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


def rotate_session_secret() -> str:
    data = _load()
    generated = secrets.token_urlsafe(48)
    data["session_secret"] = generated
    _save(data)
    return generated


def _argon2_hasher():
    from argon2 import PasswordHasher

    return PasswordHasher(
        time_cost=3,
        memory_cost=65536,
        parallelism=2,
        hash_len=32,
        salt_len=16,
    )


def _hash_password(password: str) -> dict[str, str]:
    """Prefer Argon2id; fall back to scrypt if argon2-cffi is unavailable."""
    try:
        hashed = _argon2_hasher().hash(password)
        return {
            "password_algo": ALGO_ARGON2ID,
            "password_hash": hashed,
            "password_salt": "",
        }
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Argon2 unavailable (%s); using scrypt", exc)
        salt = secrets.token_bytes(32)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
            dklen=64,
        )
        return {
            "password_algo": ALGO_SCRYPT,
            "password_hash": digest.hex(),
            "password_salt": salt.hex(),
        }


def _verify_password(password: str, data: dict[str, Any]) -> bool:
    algo = str(data.get("password_algo") or ALGO_SCRYPT)
    hash_value = data.get("password_hash")
    if not isinstance(hash_value, str) or not hash_value:
        return False

    if algo == ALGO_ARGON2ID:
        try:
            from argon2.exceptions import VerifyMismatchError

            _argon2_hasher().verify(hash_value, password)
            return True
        except VerifyMismatchError:
            return False
        except Exception:
            return False

    salt_hex = data.get("password_salt")
    if not isinstance(salt_hex, str):
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_value)
    except ValueError:
        return False
    supplied = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=64,
    )
    return hmac.compare_digest(supplied, expected)


def create_admin(username: str, password: str) -> None:
    username = username.strip()
    if not username:
        raise ValueError("Username cannot be empty.")
    if len(username) > 64:
        raise ValueError("Username cannot be longer than 64 characters.")
    validate_password(password)
    data = _load()
    if is_configured():
        raise ValueError("MineBox authentication is already configured.")
    hashed = _hash_password(password)
    data.update(
        {
            "username": username,
            **hashed,
            "session_secret": data.get("session_secret", secrets.token_urlsafe(48)),
        }
    )
    _save(data)
    LOGGER.info("Administrator account created for user=%s algo=%s", username, hashed["password_algo"])


def verify_credentials(username: str, password: str) -> bool:
    data = _load()
    stored_username = data.get("username")
    if not isinstance(stored_username, str):
        return False
    if not hmac.compare_digest(username.strip(), stored_username):
        return False
    ok = _verify_password(password, data)
    # Transparent upgrade from scrypt → argon2id on successful login.
    if ok and data.get("password_algo") != ALGO_ARGON2ID:
        try:
            hashed = _hash_password(password)
            data.update(hashed)
            _save(data)
        except Exception:
            pass
    return ok


def change_password(current_password: str, new_password: str) -> None:
    data = _load()
    username = get_username()
    if not verify_credentials(username, current_password):
        raise ValueError("Current password is incorrect.")
    validate_password(new_password)
    if hmac.compare_digest(current_password, new_password):
        raise ValueError("New password must be different from the current password.")
    hashed = _hash_password(new_password)
    data.update(hashed)
    data["password_changed_at"] = (
        __import__("datetime")
        .datetime.now(__import__("datetime").timezone.utc)
        .isoformat()
    )
    _save(data)
    LOGGER.info("Administrator password changed for user=%s", username)


def clear_admin_credentials() -> None:
    """Used by factory reset — removes dashboard auth (not worlds)."""
    data = _load()
    for key in (
        "username",
        "password_hash",
        "password_salt",
        "password_algo",
        "password_changed_at",
    ):
        data.pop(key, None)
    if "session_secret" in data:
        data["session_secret"] = secrets.token_urlsafe(48)
    _save(data)


def security_reminder_status() -> dict[str, Any]:
    data = _load()
    dismissed = bool(data.get("security_reminder_dismissed"))
    return {
        "dismissed": dismissed,
        "show_reminder": not dismissed,
        "message": (
            "Change the MineBox admin password and complete first-boot "
            "credential rotation before exposing this device on a network."
        ),
    }


def dismiss_security_reminder() -> None:
    data = _load()
    data["security_reminder_dismissed"] = True
    _save(data)


def password_algo() -> str:
    data = _load()
    return str(data.get("password_algo") or ALGO_SCRYPT)
