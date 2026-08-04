from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from services import join_access


router = APIRouter(
    prefix="/api/v1/join",
    tags=["Join"],
)


@router.get("/status")
def get_join_status() -> dict[str, Any]:
    return join_access.status()


@router.post("/refresh-avahi")
def refresh_avahi() -> dict[str, Any]:
    result = join_access.ensure_avahi_advertisement()
    if not result.ok:
        raise HTTPException(status_code=500, detail=result.message)
    return {
        "ok": True,
        "message": result.message,
        "join": join_access.status(),
    }


@router.post("/internet/enable")
def enable_internet() -> dict[str, Any]:
    result = join_access.enable_upnp()
    status = join_access.status()
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={
                "message": result.get("message"),
                "join": status,
            },
        )
    return {
        "ok": True,
        "message": result.get("message"),
        "join": status,
    }


@router.post("/internet/disable")
def disable_internet() -> dict[str, Any]:
    result = join_access.disable_upnp()
    return {
        "ok": bool(result.get("ok")),
        "message": result.get("message"),
        "join": join_access.status(),
    }
