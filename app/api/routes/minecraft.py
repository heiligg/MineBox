from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from services import minecraft

router = APIRouter(
    prefix="/api/v1/minecraft",
    tags=["Minecraft"],
)


def minecraft_status() -> dict[str, Any]:
    return {
        "running": minecraft.is_running(),
        "status": minecraft.status_text(),
        "players": minecraft.player_count_text(),
        "version": minecraft.version(),
        "uptime": minecraft.uptime(),
    }


def run_action(action: str, fn: Callable[[], Any]) -> dict[str, Any]:
    result = fn()

    payload = {
        "ok": bool(result.ok),
        "action": action,
        "message": result.stdout or result.stderr,
        "minecraft": minecraft_status(),
    }

    if not result.ok:
        raise HTTPException(status_code=500, detail=payload)

    return payload


@router.get("")
def status() -> dict[str, Any]:
    return {
        "ok": True,
        "minecraft": minecraft_status(),
    }


@router.post("/start")
def start():
    return run_action("start", minecraft.start)


@router.post("/stop")
def stop():
    return run_action("stop", minecraft.stop)


@router.post("/restart")
def restart():
    return run_action("restart", minecraft.restart)
