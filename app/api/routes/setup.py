from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import downloads, installer, servers


router = APIRouter(prefix="/api/v1/setup", tags=["setup"])

LEGACY_MINECRAFT_DIR = Path("/opt/minecraft")
LEGACY_SERVER_JAR = LEGACY_MINECRAFT_DIR / "server.jar"
LEGACY_SERVER_PROPERTIES = LEGACY_MINECRAFT_DIR / "server.properties"
SETUP_MARKER = servers.METADATA_DIR / ".minebox-setup-complete"


class CreateServerRequest(BaseModel):
    server_name: str = Field(default="My MineBox Server", min_length=1, max_length=100)
    memory_gb: int = Field(default=4, ge=1, le=64)
    version: str = Field(min_length=1, max_length=40)
    server_id: str | None = Field(default=None, min_length=1, max_length=48)
    overwrite: bool = False


def legacy_server_exists() -> bool:
    return LEGACY_SERVER_JAR.is_file() and LEGACY_SERVER_PROPERTIES.is_file()


def setup_complete() -> bool:
    return SETUP_MARKER.is_file() or bool(servers.list_servers())


def write_setup_marker() -> None:
    servers.ensure_layout()
    SETUP_MARKER.write_text("MineBox setup completed.\n", encoding="utf-8")


@router.get("/status")
def setup_status():
    instances = servers.list_servers()
    active = servers.active_server()
    return {
        "success": True,
        "complete": setup_complete(),
        "server_exists": bool(instances),
        "legacy_server_exists": legacy_server_exists(),
        "server_count": len(instances),
        "active_server_id": active.server_id if active else None,
        "servers": [instance.__dict__ for instance in instances],
    }


@router.get("/versions")
def list_versions(include_snapshots: bool = Query(default=False)):
    try:
        versions = downloads.available_versions(include_snapshots=include_snapshots)
        return {"success": True, "count": len(versions), "versions": versions}
    except downloads.DownloadError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/complete")
def complete_existing_server():
    if not legacy_server_exists() and not servers.list_servers():
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
        "migration_required": legacy_server_exists() and not bool(servers.list_servers()),
    }


@router.post("/create", status_code=201)
def create_server(request: CreateServerRequest):
    instance = None
    server_dir = None

    try:
        instance = servers.reserve_server(
            name=request.server_name,
            version=request.version,
            memory_gb=request.memory_gb,
            server_id=request.server_id,
        )
        server_dir = Path(instance.directory)

        install_result = installer.initialize(instance)
        download_result = downloads.download_server(
            version_id=request.version,
            server_dir=server_dir,
            overwrite=request.overwrite,
        )
        servers.set_active_server(instance.server_id)
        write_setup_marker()

        return {
            "success": True,
            "server_id": instance.server_id,
            "server_name": instance.name,
            "memory_gb": instance.memory_gb,
            "version": instance.version,
            "port": instance.port,
            "rcon_port": instance.rcon_port,
            "directory": install_result["directory"],
            "server_jar": download_result["file"],
            "size_bytes": download_result["size_bytes"],
            "sha1": download_result["sha1"],
        }

    except (downloads.DownloadError, servers.ServerManagerError) as error:
        if server_dir is not None:
            shutil.rmtree(server_dir, ignore_errors=True)
        if instance is not None:
            servers.remove_server_record(instance.server_id)
        raise HTTPException(status_code=400, detail=str(error)) from error

    except OSError as error:
        if server_dir is not None:
            shutil.rmtree(server_dir, ignore_errors=True)
        if instance is not None:
            servers.remove_server_record(instance.server_id)
        raise HTTPException(
            status_code=500,
            detail=f"Could not create the server files: {error}",
        ) from error
