"""Shared status endpoints for web + display UIs (Checkpoint 2 foundation)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from core.state_service import get_state_service
from hardware.factory import get_hardware

router = APIRouter(prefix="/api/v1", tags=["Foundation"])


@router.get("/status/foundation")
def foundation_status() -> dict[str, Any]:
    """Aggregate read-only appliance status. Never includes secrets."""
    return get_state_service().public_status()


@router.get("/status/setup")
def setup_bootstrap_status() -> dict[str, Any]:
    return {"ok": True, "setup": get_state_service().setup_state()}


@router.get("/status/minecraft")
def minecraft_state_status() -> dict[str, Any]:
    return {"ok": True, "minecraft": get_state_service().minecraft_state()}


@router.get("/status/system")
def system_state_status() -> dict[str, Any]:
    return {"ok": True, "system": get_state_service().system_health()}


@router.get("/status/hardware")
def hardware_state_status() -> dict[str, Any]:
    return {"ok": True, "hardware": get_state_service().hardware_status()}


@router.get("/hardware/diag")
def hardware_diag() -> dict[str, Any]:
    """Live input/capability snapshot without triggering power actions."""
    hw = get_hardware()
    snap = hw.diagnostic_snapshot()
    # Strip any accidental secret-like keys.
    snap.pop("secrets", None)
    return {
        "ok": True,
        "diagnostic": snap,
        "note": "Diagnostic only — shutdown/reboot are not invoked by this endpoint.",
    }


@router.get("/providers")
def list_providers() -> dict[str, Any]:
    return {"ok": True, "providers": get_state_service().provider_capabilities()}


@router.get("/status/operations")
def operations_status() -> dict[str, Any]:
    from services.operations import get_coordinator

    coord = get_coordinator()
    return {"ok": True, "current": coord.current(), "history": coord.history()}


@router.get("/status/thermal")
def thermal_status() -> dict[str, Any]:
    from services import thermal

    return {"ok": True, "thermal": thermal.update()}


@router.get("/status/crash")
def crash_status() -> dict[str, Any]:
    from services import crash_recovery

    return {"ok": True, "crash": crash_recovery.status()}


@router.get("/status/backups")
def backups_summary() -> dict[str, Any]:
    from services import backups

    status = backups.backup_status()
    # Avoid dumping full backup paths unnecessarily in foundation summary.
    return {
        "ok": True,
        "backup_count": status.get("backup_count"),
        "busy": status.get("busy"),
        "retention": status.get("retention"),
        "automatic_backup_hours": status.get("automatic_backup_hours"),
        "backups": [
            {
                "filename": item.get("filename"),
                "size": item.get("size"),
                "created_at": item.get("created_at"),
            }
            for item in (status.get("backups") or [])
        ],
    }
