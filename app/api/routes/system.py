from fastapi import APIRouter
from typing import Any

from services import monitoring

router = APIRouter(
    prefix="/api/v1",
    tags=["System"],
)


def system_status() -> dict[str, Any]:
    sample = monitoring.sample()

    return {
        "cpu_percent": sample.cpu,
        "memory_percent": sample.memory,
        "minecraft_memory_mb": sample.server_memory_mb,
    }


@router.get("/system")
def get_system_status() -> dict[str, Any]:
    return {
        "ok": True,
        "system": system_status(),
    }


@router.get("/status")
def get_status() -> dict[str, Any]:
    from services import minecraft

    return {
        "ok": True,
        "system": system_status(),
        "minecraft": {
            "running": minecraft.is_running(),
            "status": minecraft.status_text(),
            "players": minecraft.player_count_text(),
            "version": minecraft.version(),
            "uptime": minecraft.uptime(),
        },
    }
