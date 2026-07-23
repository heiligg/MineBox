from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import servers


router = APIRouter(prefix="/api/v1/servers", tags=["servers"])


class SelectServerRequest(BaseModel):
    server_id: str = Field(min_length=1, max_length=48)


def _serialize(instance: servers.ServerInstance, active_id: str | None) -> dict:
    return {
        "server_id": instance.server_id,
        "name": instance.name,
        "directory": instance.directory,
        "version": instance.version,
        "memory_gb": instance.memory_gb,
        "port": instance.port,
        "rcon_port": instance.rcon_port,
        "active": instance.server_id == active_id,
    }


@router.get("")
def list_server_instances():
    try:
        active_id = servers.active_server_id()
        instances = servers.list_servers()
        return {
            "success": True,
            "active_server_id": active_id,
            "count": len(instances),
            "servers": [_serialize(instance, active_id) for instance in instances],
        }
    except servers.ServerManagerError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/active")
def get_active_server():
    try:
        instance = servers.active_server()
        if instance is None:
            raise HTTPException(status_code=404, detail="No server instance exists.")
        return {"success": True, "server": _serialize(instance, instance.server_id)}
    except servers.ServerManagerError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/active")
def select_active_server(request: SelectServerRequest):
    try:
        instance = servers.set_active_server(request.server_id)
        return {
            "success": True,
            "message": f"'{instance.name}' is now the active server.",
            "server": _serialize(instance, instance.server_id),
        }
    except servers.ServerManagerError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
