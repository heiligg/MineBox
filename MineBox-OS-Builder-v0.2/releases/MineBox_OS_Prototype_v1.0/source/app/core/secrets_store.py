"""Secrets loading, generation, redaction, and migration helpers.

Never log secret values. Prefer per-server RCON files over a shared password.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Iterable

LOGGER = logging.getLogger("minebox.secrets")

# Temporary image-bootstrap values only — must be rotated during first boot.
BOOTSTRAP_HOTSPOT_PSK = "mineboxsetup"
LEGACY_HARDCODED_RCON = "MineBoxLocalRcon"

SECRET_ENV_KEYS = (
    "MINEBOX_SESSION_SECRET",
    "HOTSPOT_PSK",
    "RCON_PASSWORD",
    "TAILSCALE_AUTHKEY",
    "SESSION_SECRET",
)


class SecretsError(Exception):
    pass


def _runtime_dir() -> Path:
    return Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox"))


def default_secrets_paths() -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get("MINEBOX_SECRETS_FILE")
    if env:
        paths.append(Path(env).expanduser())
    try:
        from core.minebox_config import get_config

        paths.append(Path(get_config().secrets_file))
    except Exception:  # noqa: BLE001
        paths.append(Path("/etc/minebox/secrets.env"))
    paths.append(_runtime_dir() / "secrets.env")
    return paths


def parse_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SecretsError(f"Cannot read secrets file {path}: {exc}") from exc
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            result[key] = value
    return result


def load_secrets_map() -> dict[str, str]:
    """Merge secrets from the first existing file + process environment."""
    merged: dict[str, str] = {}
    for path in default_secrets_paths():
        if path.is_file():
            try:
                merged.update(parse_env_file(path))
            except SecretsError as exc:
                LOGGER.warning("Skipping secrets file: %s", exc)
            break
    for key in SECRET_ENV_KEYS:
        env_val = os.environ.get(key)
        if env_val:
            merged[key] = env_val
    return merged


def ensure_secure_permissions(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


def write_secrets_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    lines = [
        "# MineBox secrets — mode 0600. Do not commit.",
        "# Generated/updated by MineBox; rotate via first-boot / settings.",
    ]
    for key in sorted(values):
        lines.append(f"{key}={values[key]}")
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ensure_secure_permissions(tmp)
    tmp.replace(path)
    ensure_secure_permissions(path)


def generate_rcon_password() -> str:
    return secrets.token_urlsafe(18)


def get_or_create_runtime_secret(key: str, generator) -> str:
    runtime = _runtime_dir() / "secrets.env"
    values: dict[str, str] = {}
    if runtime.is_file():
        try:
            values = parse_env_file(runtime)
        except SecretsError:
            values = {}
    existing = values.get(key) or load_secrets_map().get(key)
    if existing:
        return existing
    created = generator()
    values[key] = created
    try:
        write_secrets_file(runtime, values)
    except OSError as exc:
        LOGGER.warning("Could not persist runtime secret %s: %s", key, exc)
    return created


def get_hotspot_psk() -> str | None:
    value = load_secrets_map().get("HOTSPOT_PSK")
    return value or None


def is_bootstrap_hotspot_psk(value: str | None) -> bool:
    return bool(value) and value == BOOTSTRAP_HOTSPOT_PSK


def get_rcon_password() -> str:
    """Shared RCON fallback for migration only.

    Prefer per-server `.minebox-rcon-password`. Never returns the former
    hard-coded production constant unless it is still present in a migrated
    secrets file (and then first-boot marks it for rotation).
    """
    mapped = load_secrets_map().get("RCON_PASSWORD", "").strip()
    if mapped and mapped != LEGACY_HARDCODED_RCON:
        return mapped
    # Do not invent a shared universal password for new installs.
    return get_or_create_runtime_secret("RCON_PASSWORD", generate_rcon_password)


def get_or_create_server_rcon_password(server_dir: Path) -> str:
    password_file = server_dir / ".minebox-rcon-password"
    if password_file.is_file():
        try:
            existing = password_file.read_text(encoding="utf-8").strip()
        except OSError:
            existing = ""
        if existing and existing != LEGACY_HARDCODED_RCON:
            return existing
        if existing == LEGACY_HARDCODED_RCON:
            # Rotate away from the old hard-coded value.
            existing = ""
    password = generate_rcon_password()
    try:
        server_dir.mkdir(parents=True, exist_ok=True)
        password_file.write_text(password + "\n", encoding="utf-8")
        ensure_secure_permissions(password_file)
    except OSError as exc:
        LOGGER.warning("Could not write RCON password file: %s", exc)
    return password


def get_session_secret_override() -> str | None:
    mapped = load_secrets_map()
    for key in ("MINEBOX_SESSION_SECRET", "SESSION_SECRET"):
        value = mapped.get(key)
        if isinstance(value, str) and len(value) >= 32:
            return value
    return None


def get_tailscale_authkey() -> str | None:
    value = load_secrets_map().get("TAILSCALE_AUTHKEY")
    return value or None


def secret_values_for_redaction() -> list[str]:
    values = []
    for key, value in load_secrets_map().items():
        if value and key in SECRET_ENV_KEYS:
            values.append(value)
    values.append(BOOTSTRAP_HOTSPOT_PSK)
    values.append(LEGACY_HARDCODED_RCON)
    return [v for v in values if len(v) >= 4]


def redact_secrets(text: str, extra: Iterable[str] | None = None) -> str:
    """Replace known secret substrings for safe logging/support bundles."""
    if not text:
        return text
    redacted = text
    candidates = list(secret_values_for_redaction())
    if extra:
        candidates.extend(extra)
    # Longest first to avoid partial overlaps leaving remnants.
    for secret in sorted(set(candidates), key=len, reverse=True):
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    # Common key=value patterns.
    redacted = re.sub(
        r"(?i)\b(rcon\.password|wpa_passphrase|password|psk|authkey|token)\s*[=:]\s*\S+",
        r"\1=[REDACTED]",
        redacted,
    )
    return redacted


def credentials_needing_rotation() -> list[str]:
    """List credential kinds still at bootstrap/legacy defaults."""
    pending: list[str] = []
    psk = get_hotspot_psk()
    if psk is None or is_bootstrap_hotspot_psk(psk):
        pending.append("hotspot_psk")
    mapped = load_secrets_map().get("RCON_PASSWORD", "")
    if mapped == LEGACY_HARDCODED_RCON:
        pending.append("rcon_password")
    return pending
