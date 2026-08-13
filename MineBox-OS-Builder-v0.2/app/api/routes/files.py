from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services import files


router = APIRouter(
    prefix="/api/v1/files",
    tags=["Files"],
)


class MkdirRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=2048)


def _status_for(message: str) -> int:
    normalized = message.lower()
    if "not found" in normalized or "missing" in normalized:
        return 404
    if "stop the minecraft server" in normalized:
        return 409
    if (
        "not allowed" in normalized
        or "outside" in normalized
        or "invalid" in normalized
        or "exceeds" in normalized
        or "cannot delete" in normalized
        or "choose a" in normalized
        or "no active" in normalized
        or "already exists" in normalized
    ):
        return 400
    return 500


def _http_error(error: files.FilesError) -> HTTPException:
    message = str(error)
    return HTTPException(status_code=_status_for(message), detail=message)


def _parent_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip().strip("/")
    if not normalized or "/" not in normalized:
        return ""
    return normalized.rsplit("/", 1)[0]


@router.get("")
def list_files(path: str = Query(default="")) -> dict[str, Any]:
    try:
        payload = files.list_directory(path)
    except files.FilesError as error:
        raise _http_error(error) from error
    return {"ok": True, **payload}


@router.get("/download")
def download_file(path: str = Query(...)) -> FileResponse:
    try:
        target = files.download_path(path)
    except files.FilesError as error:
        raise _http_error(error) from error
    return FileResponse(
        path=target,
        filename=target.name,
        media_type="application/octet-stream",
    )


@router.post("/mkdir")
def create_directory(body: MkdirRequest) -> dict[str, Any]:
    try:
        result = files.ensure_directory(body.path)
        listing = files.list_directory(_parent_path(body.path))
    except files.FilesError as error:
        raise _http_error(error) from error
    return {"ok": True, **result, **listing}


@router.post("/upload")
async def upload_file(
    path: str = Form(default=""),
    relative_path: str = Form(default=""),
    file: UploadFile = File(...),
    refresh: bool = Query(default=True),
    nested: str = Query(default=""),
    x_minebox_relative_path: str | None = Header(
        default=None,
        alias="X-MineBox-Relative-Path",
    ),
) -> dict[str, Any]:
    try:
        result = await files.upload_file(
            path,
            file,
            relative_path=relative_path or None,
            extra_paths=[nested, x_minebox_relative_path or ""],
        )
        if not refresh:
            return {"ok": True, **result}
        listing = files.list_directory(path)
    except files.FilesError as error:
        raise _http_error(error) from error
    return {"ok": True, **result, **listing}


@router.delete("")
def delete_file(path: str = Query(...)) -> dict[str, Any]:
    try:
        result = files.delete_path(path)
        listing = files.list_directory(_parent_path(path))
    except files.FilesError as error:
        raise _http_error(error) from error
    return {"ok": True, **result, **listing}
