"""Tailscale / remote-access API (authenticated, CSRF, rate-limited)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.rate_limit import check_rate_limit, client_key, clear, record_failure
from networking import remote_access

router = APIRouter(prefix="/api/v1/remote-access", tags=["Remote Access"])


class EnableRequest(BaseModel):
    auth_key: str = Field(min_length=20, max_length=200)
    expose_dashboard: bool = False
    expose_minecraft: bool = False


class ConfirmRequest(BaseModel):
    confirm: bool = False


class ExposureRequest(BaseModel):
    expose_dashboard: bool | None = None
    expose_minecraft: bool | None = None


def _provider() -> remote_access.TailscaleRemoteAccessProvider:
    provider = remote_access.get_remote_access_provider()
    if not isinstance(provider, remote_access.TailscaleRemoteAccessProvider):
        raise HTTPException(status_code=500, detail="Remote-access provider unavailable.")
    return provider


@router.get("/status")
def get_status(request: Request) -> dict[str, Any]:
    authenticated = request.session.get("authenticated") is True
    status = _provider().status(authenticated=authenticated)
    return {"ok": True, **status.to_public_dict(authenticated=authenticated)}


@router.post("/enable")
async def enable(request: Request, body: EnableRequest) -> dict[str, Any]:
    key = client_key(request, "remote-enable")
    allowed, retry = check_rate_limit(key, max_attempts=5, window_s=600, cooldown_s=180)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Too many attempts. Retry in {int(retry)}s.")
    try:
        # Auth key only in body — never query string.
        status = _provider().enable(
            auth_key=body.auth_key,
            expose_dashboard=body.expose_dashboard,
            expose_minecraft=body.expose_minecraft,
        )
        clear(key)
        return {"ok": True, **status.to_public_dict(authenticated=True)}
    except ValueError as exc:
        record_failure(key)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/disable")
def disable(body: ConfirmRequest) -> dict[str, Any]:
    try:
        status = _provider().disable(confirm=body.confirm)
        return {"ok": True, **status.to_public_dict(authenticated=True)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/logout")
def logout(body: ConfirmRequest) -> dict[str, Any]:
    try:
        status = _provider().logout(confirm=body.confirm)
        return {"ok": True, **status.to_public_dict(authenticated=True)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/exposure")
def exposure(body: ExposureRequest) -> dict[str, Any]:
    try:
        status = _provider().set_exposure(
            expose_dashboard=body.expose_dashboard,
            expose_minecraft=body.expose_minecraft,
        )
        return {"ok": True, **status.to_public_dict(authenticated=True)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
