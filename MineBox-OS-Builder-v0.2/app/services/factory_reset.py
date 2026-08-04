"""Factory reset that preserves worlds/backups by default."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.bootstrap import save_bootstrap_file
from services import auth
from services.first_boot import save_wizard, wizard_path

LOGGER = logging.getLogger("minebox.factory_reset")


class FactoryResetError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _runtime_dir() -> Path:
    return Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox"))


def issue_recovery_token() -> str:
    token = secrets.token_urlsafe(24)
    path = _runtime_dir() / "recovery_token"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return token


def verify_recovery_token(token: str) -> bool:
    path = _runtime_dir() / "recovery_token"
    if not path.is_file():
        return False
    try:
        stored = path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return bool(stored) and secrets.compare_digest(stored, (token or "").strip())


def factory_reset(
    *,
    confirm: bool,
    erase_worlds: bool = False,
    confirm_erase_phrase: str = "",
    admin_password: str = "",
    recovery_token: str = "",
) -> dict[str, Any]:
    if not confirm:
        raise FactoryResetError("Factory reset requires confirm=true.")

    authed = False
    if admin_password and auth.is_configured():
        authed = auth.verify_credentials(auth.get_username(), admin_password)
    if not authed and recovery_token:
        authed = verify_recovery_token(recovery_token)
    if not authed:
        raise FactoryResetError(
            "Provide the administrator password or a valid local recovery token."
        )

    if erase_worlds:
        if confirm_erase_phrase.strip() != "ERASE WORLDS":
            raise FactoryResetError(
                'Full data erase requires confirm_erase_phrase exactly "ERASE WORLDS".'
            )

    # Clear auth + setup flags.
    auth.clear_admin_credentials()
    save_bootstrap_file(
        {
            "first_boot_complete": False,
            "rotated": [],
            "os_password_rotated": False,
            "factory_reset_at": datetime.now(timezone.utc).isoformat(),
            "erase_worlds": bool(erase_worlds),
        }
    )
    save_wizard({"step": "admin", "data": {}})
    for name in ("first_boot_complete", "first_boot_wizard.json"):
        (_runtime_dir() / name).unlink(missing_ok=True)

    # Clear Minecraft setup marker but keep servers/worlds unless erase requested.
    try:
        from services import servers

        marker = servers.METADATA_DIR / ".minebox-setup-complete"
        marker.unlink(missing_ok=True)
        if erase_worlds:
            for instance in servers.list_servers():
                servers.delete_server(instance.server_id)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Server cleanup warning: %s", exc)

    # Clear hotspot PSK back to unset (forces rotation) — do not write bootstrap default.
    try:
        from core import secrets_store

        runtime = _runtime_dir() / "secrets.env"
        values = {}
        if runtime.is_file():
            values = secrets_store.parse_env_file(runtime)
        values.pop("HOTSPOT_PSK", None)
        values.pop("RCON_PASSWORD", None)
        secrets_store.write_secrets_file(runtime, values)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Secrets cleanup warning: %s", exc)

    recovery = issue_recovery_token()
    LOGGER.info(
        "Factory reset complete erase_worlds=%s (recovery token issued to runtime file)",
        erase_worlds,
    )
    return {
        "ok": True,
        "worlds_preserved": not erase_worlds,
        "backups_preserved": not erase_worlds,
        "admin_cleared": True,
        "setup_complete": False,
        "recovery_token": recovery,
        "message": (
            "Factory reset completed. Worlds/backups preserved."
            if not erase_worlds
            else "Factory reset completed with world erase."
        ),
    }
