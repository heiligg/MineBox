"""First-boot / bootstrap incomplete state (no secrets in payloads)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import secrets_store


def _runtime_dir() -> Path:
    return Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox"))


def bootstrap_path() -> Path:
    return _runtime_dir() / "bootstrap.json"


@dataclass
class BootstrapState:
    first_boot_complete: bool = False
    admin_configured: bool = False
    setup_marker_present: bool = False
    credentials_rotation_required: bool = True
    pending_credential_rotations: list[str] = field(default_factory=list)
    message: str = (
        "MineBox first-boot setup is incomplete. Replace all shipped/default "
        "credentials (OS account, dashboard admin, hotspot PSK, RCON) before "
        "normal use."
    )
    updated_at: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Explicit: never attach secret values.
        data["secrets_exposed"] = False
        return data


def _auth_configured() -> bool:
    try:
        from services import auth

        return bool(auth.is_configured())
    except Exception:  # noqa: BLE001
        return False


def _setup_marker_present() -> bool:
    try:
        from api.routes.setup import setup_complete

        return bool(setup_complete())
    except Exception:  # noqa: BLE001
        marker = Path("/opt/minecraft/.minebox") / ".minebox-setup-complete"
        # servers.METADATA_DIR may differ; also check runtime flag.
        runtime_marker = _runtime_dir() / "first_boot_complete"
        return runtime_marker.is_file() or marker.is_file()


def load_bootstrap_file() -> dict[str, Any]:
    path = bootstrap_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_bootstrap_file(data: dict[str, Any]) -> None:
    path = bootstrap_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def get_bootstrap_state() -> BootstrapState:
    stored = load_bootstrap_file()
    admin_ok = _auth_configured()
    setup_ok = _setup_marker_present()
    pending = list(secrets_store.credentials_needing_rotation())
    if not admin_ok:
        pending = list(dict.fromkeys(["dashboard_admin", *pending]))
    # OS password rotation is tracked when first-boot marks it (Checkpoint 4).
    if not stored.get("os_password_rotated"):
        pending = list(dict.fromkeys([*pending, "os_account_password"]))

    forced_complete = bool(stored.get("first_boot_complete"))
    rotation_required = bool(pending) or not (admin_ok and setup_ok)
    first_boot_complete = forced_complete and admin_ok and not rotation_required

    message = (
        "MineBox first-boot setup is complete."
        if first_boot_complete
        else (
            "MineBox first-boot setup is incomplete. Replace all shipped/default "
            "credentials (OS account, dashboard admin, hotspot PSK, RCON) before "
            "normal use."
        )
    )

    return BootstrapState(
        first_boot_complete=first_boot_complete,
        admin_configured=admin_ok,
        setup_marker_present=setup_ok,
        credentials_rotation_required=rotation_required,
        pending_credential_rotations=pending,
        message=message,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def mark_credential_rotated(kind: str) -> None:
    data = load_bootstrap_file()
    rotated = list(data.get("rotated") or [])
    if kind not in rotated:
        rotated.append(kind)
    data["rotated"] = rotated
    if kind == "os_account_password":
        data["os_password_rotated"] = True
    if kind == "hotspot_psk":
        data["hotspot_psk_rotated"] = True
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_bootstrap_file(data)
