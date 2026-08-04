from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import minecraft, settings, servers


router = APIRouter(
    prefix="/api/v1/appliance",
    tags=["Appliance"],
)


class ApplianceUpdateRequest(BaseModel):
    scheduled_restart_time: str | None = Field(default=None, max_length=8)
    automatic_backup_hours: int | None = Field(default=None, ge=0, le=720)
    memory_gb: int | None = Field(default=None, ge=1, le=64)


def _normalize_restart_time(value: str) -> str:
    clean = (value or "").strip()
    if not clean:
        return ""
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", clean)
    if not match:
        raise ValueError("Use HH:MM (24-hour), such as 04:30, or leave blank.")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Use HH:MM (24-hour), such as 04:30, or leave blank.")
    return f"{hour:02d}:{minute:02d}"


def _payload() -> dict[str, Any]:
    cfg = settings.load()
    active = servers.active_server()
    return {
        "ok": True,
        "scheduled_restart_time": str(cfg.get("scheduled_restart_time") or ""),
        "automatic_backup_hours": int(cfg.get("automatic_backup_hours") or 0),
        "backup_retention": int(cfg.get("backup_retention") or 10),
        "memory_gb": int(active.memory_gb) if active else None,
        "server_id": active.server_id if active else None,
        "server_running": minecraft.is_running(),
        "restart_required_for_memory": False,
    }


@router.get("")
def get_appliance() -> dict[str, Any]:
    return _payload()


@router.put("")
def put_appliance(body: ApplianceUpdateRequest) -> dict[str, Any]:
    cfg = settings.load()
    messages: list[str] = []
    restart_for_memory = False

    if body.scheduled_restart_time is not None:
        try:
            cfg["scheduled_restart_time"] = _normalize_restart_time(
                body.scheduled_restart_time
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        messages.append(
            "Daily restart "
            + (
                f"set to {cfg['scheduled_restart_time']}."
                if cfg["scheduled_restart_time"]
                else "disabled."
            )
        )

    if body.automatic_backup_hours is not None:
        cfg["automatic_backup_hours"] = int(body.automatic_backup_hours)
        hours = cfg["automatic_backup_hours"]
        messages.append(
            f"Automatic backups every {hours}h."
            if hours
            else "Automatic backups disabled."
        )

    ok, save_message = settings.save(cfg)
    if not ok:
        raise HTTPException(status_code=500, detail=save_message)

    if body.memory_gb is not None:
        try:
            instance = servers.update_memory_gb(None, body.memory_gb)
        except servers.ServerManagerError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        restart_for_memory = minecraft.is_running()
        messages.append(
            f"JVM memory set to {instance.memory_gb}G"
            + (
                " (restart required to apply)."
                if restart_for_memory
                else "."
            )
        )

    payload = _payload()
    payload["restart_required_for_memory"] = restart_for_memory
    payload["message"] = " ".join(messages) if messages else "Appliance settings saved."
    return payload
