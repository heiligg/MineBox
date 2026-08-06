from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import minecraft, servers

router = APIRouter(prefix="/api/v1/servers", tags=["servers"])


class SelectServerRequest(BaseModel):
    server_id: str = Field(min_length=1, max_length=48)


class ConfirmRequest(BaseModel):
    confirm: bool = False


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
            "servers": [_serialize(item, active_id) for item in instances],
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
        target = servers.get_server(request.server_id)
        current = servers.active_server()
        if current and current.server_id == target.server_id:
            # Same server selected: still ensure Java and try to bring it up.
            try:
                from services.launcher import ensure_runtime_for_active

                ensure_runtime_for_active()
            except Exception as java_exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=500,
                    detail=f"Could not prepare Java for '{target.name}': {java_exc}",
                ) from java_exc
            if not minecraft.is_running():
                result = minecraft.start()
                if not result.ok:
                    raise HTTPException(
                        status_code=500,
                        detail=result.stderr or "Could not start the selected server.",
                    )
                return {
                    "success": True,
                    "message": (
                        f"'{target.name}' is active; Java was prepared and "
                        "the server was started."
                    ),
                    "server": _serialize(target, target.server_id),
                    "restarted": True,
                }
            return {
                "success": True,
                "message": f"'{target.name}' is already active and running.",
                "server": _serialize(target, target.server_id),
                "restarted": False,
            }

        was_running = minecraft.is_running()
        if was_running:
            result = minecraft.stop()
            if not result.ok:
                raise HTTPException(
                    status_code=500,
                    detail=result.stderr or "Could not stop Minecraft.",
                )

        instance = servers.set_active_server(target.server_id)

        # Always prepare the Java runtime for this server's version, then start.
        try:
            from services.launcher import ensure_runtime_for_active

            ensure_runtime_for_active()
        except Exception as java_exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Switched to '{instance.name}', but Java install failed: "
                    f"{java_exc}"
                ),
            ) from java_exc

        result = minecraft.start()
        if not result.ok:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Switched to '{instance.name}', but start failed: "
                    f"{result.stderr or 'unknown error'}"
                ),
            )

        return {
            "success": True,
            "message": (
                f"'{instance.name}' is now active"
                + (" (previous server stopped)" if was_running else "")
                + "; Java prepared and server started."
            ),
            "server": _serialize(instance, instance.server_id),
            "restarted": True,
        }
    except HTTPException:
        raise
    except servers.ServerManagerError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/{server_id}")
def delete_server_instance(server_id: str, body: ConfirmRequest | None = None):
    if not body or not body.confirm:
        raise HTTPException(status_code=400, detail="Server deletion requires confirm=true.")
    try:
        instance = servers.get_server(server_id)
        if minecraft.is_running() and servers.active_server_id() == instance.server_id:
            raise HTTPException(status_code=409, detail="Switch away from this running server before deleting it.")
        deleted = servers.delete_server(server_id)
        active = servers.active_server()
        return {
            "success": True,
            "message": f"'{deleted.name}' was deleted.",
            "deleted_server_id": deleted.server_id,
            "active_server_id": active.server_id if active else None,
        }
    except HTTPException:
        raise
    except servers.ServerManagerError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
