from typing import Any

from fastapi import APIRouter

from services import minecraft
from services import monitoring


router = APIRouter(
    prefix="/api/v1",
    tags=["System"],
)


def minecraft_status() -> dict[str, Any]:
    return {
        "running": minecraft.is_running(),
        "status": minecraft.status_text(),
        "players": minecraft.player_count_text(),
        "version": minecraft.version(),
        "uptime": minecraft.uptime(),
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
