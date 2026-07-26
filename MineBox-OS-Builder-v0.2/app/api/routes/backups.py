from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services import backups


router = APIRouter(
    prefix="/api/v1/backups",
    tags=["Backups"],
)


class BackupSettingsRequest(BaseModel):
    automatic_backup_hours: int | None = Field(default=None, ge=0, le=168)
    retention: int | None = Field(default=None, ge=1, le=100)
    backup_retention: int | None = Field(default=None, ge=1, le=100)


@router.get("")
def get_backups() -> dict[str, Any]:
    return {
        "ok": True,
        **backups.backup_status(),
    }


@router.put("/settings")
def put_backup_settings(body: BackupSettingsRequest) -> dict[str, Any]:
    try:
        status = backups.update_backup_settings(
            automatic_backup_hours=body.automatic_backup_hours,
            retention=body.retention
            if body.retention is not None
            else body.backup_retention,
        )
    except backups.BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **status}


@router.post("")
def create_backup(
    retention: int | None = Query(
        default=None,
        ge=1,
        le=100,
    ),
) -> dict[str, Any]:
    try:
        keep = retention
        if keep is None:
            keep = int(backups.backup_status().get("retention") or backups.DEFAULT_RETENTION)
        result = backups.create_backup(
            retention=keep,
        )

    except backups.BackupError as exc:
        message = str(exc)

        status_code = (
            409
            if "already running" in message.lower()
            else 500
        )

        raise HTTPException(
            status_code=status_code,
            detail=message,
        ) from exc

    return {
        "ok": True,
        "backup": result,
        **backups.backup_status(),
    }

# MineBox Backup Management API v2

def _backup_error_status(message: str) -> int:
    normalized = message.lower()

    if "does not exist" in normalized:
        return 404

    if "already running" in normalized:
        return 409

    if "invalid backup filename" in normalized:
        return 400

    return 500


@router.get("/{filename}/download")
def download_backup(filename: str) -> FileResponse:
    try:
        backup_path = backups.get_backup_path(filename)

    except backups.BackupError as exc:
        message = str(exc)

        raise HTTPException(
            status_code=_backup_error_status(message),
            detail=message,
        ) from exc

    return FileResponse(
        path=backup_path,
        media_type="application/gzip",
        filename=backup_path.name,
    )


@router.delete("/{filename}")
def delete_backup(filename: str) -> dict[str, Any]:
    try:
        deleted = backups.delete_backup(filename)

    except backups.BackupError as exc:
        message = str(exc)

        raise HTTPException(
            status_code=_backup_error_status(message),
            detail=message,
        ) from exc

    return {
        "ok": True,
        "deleted_backup": deleted,
        **backups.backup_status(),
    }

# MineBox Backup Restore API v3

@router.post("/{filename}/restore")
def restore_backup(filename: str) -> dict[str, Any]:
    try:
        restored = backups.restore_backup(filename)

    except backups.BackupError as exc:
        message = str(exc)

        raise HTTPException(
            status_code=_backup_error_status(message),
            detail=message,
        ) from exc

    return {
        "ok": True,
        "restored_backup": restored,
        **backups.backup_status(),
    }


