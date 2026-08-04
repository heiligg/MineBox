from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from services import updates


router = APIRouter(
    prefix="/api/v1/update",
    tags=["Updates"],
)


def update_error_response(
    exc: updates.UpdateError,
) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail=str(exc),
    )


@router.get("/status")
def get_update_status() -> dict[str, Any]:
    return updates.status()


@router.post("/check")
def check_for_updates() -> dict[str, Any]:
    try:
        return updates.check_for_updates()
    except updates.UpdateError as exc:
        raise update_error_response(exc) from exc


@router.post("/install", status_code=202)
def install_update() -> JSONResponse:
    try:
        result = updates.install_update()
    except updates.UpdateError as exc:
        raise update_error_response(exc) from exc

    return JSONResponse(
        result,
        status_code=202,
    )


@router.get("/log")
def get_update_log(
    lines: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
) -> dict[str, Any]:
    try:
        return updates.read_update_log(lines)
    except updates.UpdateError as exc:
        raise update_error_response(exc) from exc
