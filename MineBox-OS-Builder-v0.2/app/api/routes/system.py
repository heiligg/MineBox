from typing import Any

from fastapi import APIRouter, HTTPException

from services import minecraft
from services import monitoring
from services import servers


router = APIRouter(
    prefix="/api/v1",
    tags=["System"],
)


def minecraft_status() -> dict[str, Any]:
    active = servers.active_server()

    return {
        "running": minecraft.is_running(),
        "status": minecraft.status_text(),
        "players": minecraft.player_count_text(),
        "version": minecraft.version(),
        "uptime": minecraft.uptime(),
        "server_name": active.name if active else "Minecraft Server",
        "server_id": active.server_id if active else None,
        "port": active.port if active else 25565,
        "rcon_port": active.rcon_port if active else 25575,
        "memory_gb": active.memory_gb if active else None,
        "loader": active.loader if active else "vanilla",
        "loader_version": active.loader_version if active else "",
    }


@router.get("/system")
def get_system_status() -> dict[str, Any]:
    return {
        "ok": True,
        "system": monitoring.system_status(),
    }


@router.get("/status")
def get_status() -> dict[str, Any]:
    return {
        "ok": True,
        "system": monitoring.system_status(),
        "minecraft": minecraft_status(),
    }


@router.post("/system/fan-test")
def post_fan_test() -> dict[str, Any]:
    try:
        result = monitoring.run_fan_test(duration_seconds=8)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "ok": True,
        **result,
        "system": monitoring.system_status(),
    }
