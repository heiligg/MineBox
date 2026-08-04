from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


@router.get("/system/thermal")
def get_thermal() -> dict[str, Any]:
    from services import thermal

    return {"ok": True, "thermal": thermal.update()}


class PowerRequest(BaseModel):
    confirm: bool = False


@router.post("/system/shutdown")
def post_shutdown(body: PowerRequest | None = None) -> dict[str, Any]:
    """Service-layer safe shutdown (auth + CSRF required)."""
    from core.rate_limit import check_rate_limit
    from services.safe_shutdown import request_shutdown

    if not body or not body.confirm:
        raise HTTPException(status_code=400, detail="Shutdown requires confirm=true.")
    allowed, retry = check_rate_limit("power-shutdown", max_attempts=3, window_s=600, cooldown_s=300)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Too many power requests. Retry in {int(retry)}s.")
    result = request_shutdown(reason="api", reboot=False)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result)
    return result


@router.post("/system/reboot")
def post_reboot(body: PowerRequest | None = None) -> dict[str, Any]:
    from core.rate_limit import check_rate_limit
    from services.safe_shutdown import request_shutdown

    if not body or not body.confirm:
        raise HTTPException(status_code=400, detail="Reboot requires confirm=true.")
    allowed, retry = check_rate_limit("power-reboot", max_attempts=3, window_s=600, cooldown_s=300)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Too many power requests. Retry in {int(retry)}s.")
    result = request_shutdown(reason="api", reboot=True)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result)
    return result
