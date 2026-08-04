"""First-boot wizard state, credential requirements, and completion gating."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.bootstrap import load_bootstrap_file, save_bootstrap_file
from core import secrets_store
from services import auth


def _runtime_dir() -> Path:
    return Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox"))


def wizard_path() -> Path:
    return _runtime_dir() / "first_boot_wizard.json"


def load_wizard() -> dict[str, Any]:
    path = wizard_path()
    if not path.is_file():
        return {"step": "admin", "data": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"step": "admin", "data": {}}
    return data if isinstance(data, dict) else {"step": "admin", "data": {}}


def save_wizard(data: dict[str, Any]) -> None:
    path = wizard_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    # Never persist raw passwords in wizard resume state.
    safe = dict(payload)
    nested = dict(safe.get("data") or {})
    for key in list(nested.keys()):
        if "password" in key.lower() or key.lower() in {"psk", "hotspot_psk", "rcon"}:
            nested.pop(key, None)
    safe["data"] = nested
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def minecraft_setup_done() -> bool:
    try:
        from api.routes.setup import setup_complete

        return bool(setup_complete())
    except Exception:
        return False


def required_rotations_pending() -> list[str]:
    pending: list[str] = []
    if not auth.is_configured():
        pending.append("dashboard_admin")
    boot = load_bootstrap_file()
    rotated = set(boot.get("rotated") or [])
    if "hotspot_psk" not in rotated:
        psk = secrets_store.get_hotspot_psk()
        if psk is None or secrets_store.is_bootstrap_hotspot_psk(psk):
            pending.append("hotspot_psk")
    if "rcon_password" not in rotated:
        pending.append("rcon_password")
    if not boot.get("os_password_rotated") and "os_account_password" not in rotated:
        if "os_account_password_deferred" not in rotated and not boot.get(
            "os_password_deferred"
        ):
            pending.append("os_account_password")
    return pending


def is_appliance_setup_complete() -> bool:
    # Test/dev escape hatch — never use on production appliances.
    if os.environ.get("MINEBOX_SKIP_FIRST_BOOT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return auth.is_configured()

    if not auth.is_configured() or not minecraft_setup_done():
        return False

    pending = [p for p in required_rotations_pending() if p != "os_account_password"]
    if pending:
        return False

    boot = load_bootstrap_file()
    # Explicit reopen sets first_boot_complete=False even if rotations still valid.
    if boot.get("first_boot_complete") is False:
        return False
    return True


def mark_appliance_complete() -> dict[str, Any]:
    pending = required_rotations_pending()
    # Allow OS deferred.
    blocking = [p for p in pending if p != "os_account_password"]
    if not auth.is_configured():
        raise ValueError("Administrator account is required before completing setup.")
    if not minecraft_setup_done():
        raise ValueError("Minecraft setup is required before completing first-boot.")
    if blocking:
        raise ValueError(
            "Required credentials not rotated: " + ", ".join(blocking)
        )
    data = load_bootstrap_file()
    data["first_boot_complete"] = True
    data["completed_at"] = datetime.now(timezone.utc).isoformat()
    save_bootstrap_file(data)
    # Touch runtime marker for recovery tooling.
    marker = _runtime_dir() / "first_boot_complete"
    try:
        marker.write_text("complete\n", encoding="utf-8")
    except OSError:
        pass
    return status()


def status() -> dict[str, Any]:
    wizard = load_wizard()
    pending = required_rotations_pending()
    complete = is_appliance_setup_complete()
    return {
        "complete": complete,
        "admin_configured": auth.is_configured(),
        "minecraft_setup_done": minecraft_setup_done(),
        "pending_credential_rotations": pending,
        "wizard_step": wizard.get("step"),
        "wizard_data": wizard.get("data") or {},
        "resumable": not complete,
        "message": (
            "MineBox first-boot setup is complete."
            if complete
            else (
                "MineBox first-boot setup is incomplete. "
                "Rotate shipped credentials and finish the wizard."
            )
        ),
        "secrets_exposed": False,
    }


def reopen_setup(*, confirm: bool, admin_password: str) -> dict[str, Any]:
    if not confirm:
        raise ValueError("Re-entering setup requires confirm=true.")
    if not auth.verify_credentials(auth.get_username(), admin_password):
        raise ValueError("Administrator password is incorrect.")
    data = load_bootstrap_file()
    data["first_boot_complete"] = False
    data["reopened_at"] = datetime.now(timezone.utc).isoformat()
    save_bootstrap_file(data)
    marker = _runtime_dir() / "first_boot_complete"
    marker.unlink(missing_ok=True)
    return status()
