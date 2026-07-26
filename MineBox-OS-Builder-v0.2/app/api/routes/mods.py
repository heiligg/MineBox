from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import mods


router = APIRouter(
    prefix="/api/v1/mods",
    tags=["Mods"],
)


class InstallProjectRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=128)
    version_id: str | None = Field(default=None, max_length=128)


class InstallUrlRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2000)
    filename: str | None = Field(default=None, max_length=180)


def _http_error(error: mods.ModsError) -> HTTPException:
    message = str(error)
    lower = message.lower()
    status = 400
    if "no active" in lower or "missing" in lower:
        status = 400
    elif "modrinth request failed" in lower or "download failed" in lower:
        status = 502
    elif "no compatible" in lower:
        status = 404
    return HTTPException(status_code=status, detail=message)


@router.get("")
def get_mods_context() -> dict[str, Any]:
    try:
        return {"ok": True, **mods.context()}
    except mods.ModsError as error:
        raise _http_error(error) from error


@router.get("/search")
def search_mods(
    q: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=40),
) -> dict[str, Any]:
    try:
        return mods.search(q, limit=limit)
    except mods.ModsError as error:
        raise _http_error(error) from error


@router.post("/install")
def install_from_modrinth(body: InstallProjectRequest) -> dict[str, Any]:
    try:
        return mods.install_project(body.project_id, version_id=body.version_id)
    except mods.ModsError as error:
        raise _http_error(error) from error


@router.post("/install-url")
def install_from_url(body: InstallUrlRequest) -> dict[str, Any]:
    try:
        return mods.install_url(body.url, filename=body.filename)
    except mods.ModsError as error:
        raise _http_error(error) from error
