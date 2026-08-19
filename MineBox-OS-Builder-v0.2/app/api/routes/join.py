from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import join_access
from services import playit
from services import public_dns


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


class PublicDnsClaimBody(BaseModel):
    slug: str = Field(min_length=1, max_length=40)
    token: str = Field(default="", max_length=128)


@router.post("/dns/claim")
def claim_public_dns(body: PublicDnsClaimBody) -> dict[str, Any]:
    try:
        dns = public_dns.claim(slug=body.slug, token=body.token)
    except public_dns.PublicDnsError as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc), "join": join_access.status()},
        ) from exc
    return {
        "ok": True,
        "message": dns.get("message"),
        "join": join_access.status(),
    }


@router.post("/dns/refresh")
def refresh_public_dns() -> dict[str, Any]:
    try:
        dns = public_dns.refresh()
    except public_dns.PublicDnsError as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc), "join": join_access.status()},
        ) from exc
    return {
        "ok": True,
        "message": dns.get("message"),
        "join": join_access.status(),
    }


@router.post("/dns/clear")
def clear_public_dns() -> dict[str, Any]:
    dns = public_dns.clear()
    return {
        "ok": True,
        "message": dns.get("message"),
        "join": join_access.status(),
    }


@router.post("/playit/enable")
def enable_playit() -> dict[str, Any]:
    result = playit.enable()
    status = join_access.status()
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"message": result.get("message"), "join": status},
        )
    return {
        "ok": True,
        "message": result.get("message"),
        "join": status,
    }


@router.post("/playit/disable")
def disable_playit() -> dict[str, Any]:
    result = playit.disable()
    return {
        "ok": bool(result.get("ok")),
        "message": result.get("message"),
        "join": join_access.status(),
    }
