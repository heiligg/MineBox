from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import downloads, installer


router = APIRouter(prefix="/api/v1/setup", tags=["setup"])

MINECRAFT_DIR = Path("/opt/minecraft")
SERVER_JAR = MINECRAFT_DIR / "server.jar"
SERVER_PROPERTIES = MINECRAFT_DIR / "server.properties"
SETUP_MARKER = MINECRAFT_DIR / ".minebox-setup-complete"


class CreateServerRequest(BaseModel):
    server_name: str = Field(
        default="My MineBox Server",
        min_length=1,
        max_length=100,
    )

    memory_gb: int = Field(
        default=4,
        ge=1,
        le=64,
    )

    version: str = Field(
        min_length=1,
        max_length=40,
    )

    overwrite: bool = False


def server_exists() -> bool:
    return SERVER_JAR.is_file() and SERVER_PROPERTIES.is_file()


def setup_complete() -> bool:
    return SETUP_MARKER.is_file() or server_exists()


def write_setup_marker() -> None:
    MINECRAFT_DIR.mkdir(parents=True, exist_ok=True)
    SETUP_MARKER.write_text(
        "MineBox setup completed.\n",
        encoding="utf-8",
    )


@router.get("/status")
def setup_status():
    return {
        "success": True,
        "complete": setup_complete(),
        "server_exists": server_exists(),
        "server_jar": str(SERVER_JAR),
    }


@router.get("/versions")
def list_versions(
    include_snapshots: bool = Query(default=False),
):
    try:
        versions = downloads.available_versions(
            include_snapshots=include_snapshots
        )

        return {
            "success": True,
            "count": len(versions),
            "versions": versions,
        }

    except downloads.DownloadError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error


@router.post("/complete")
def complete_existing_server():
    if not server_exists():
        raise HTTPException(
            status_code=400,
            detail="No existing Minecraft server was found.",
        )

    try:
        write_setup_marker()
    except OSError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Could not save setup status: {error}",
        ) from error

    return {
        "success": True,
        "message": "Existing Minecraft server accepted.",
    }


@router.post("/create")
def create_server(request: CreateServerRequest):
    try:
        install_result = installer.initialize(
            server_name=request.server_name,
            memory_gb=request.memory_gb,
        )

        download_result = downloads.download_server(
            version_id=request.version,
            overwrite=request.overwrite,
        )

        write_setup_marker()

        return {
            "success": True,
            "server_name": request.server_name,
            "memory_gb": request.memory_gb,
            "version": request.version,
            "directory": install_result["directory"],
            "server_jar": download_result["file"],
            "size_bytes": download_result["size_bytes"],
            "sha1": download_result["sha1"],
        }

    except downloads.DownloadError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except OSError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Could not create the server files: {error}",
        ) from error
