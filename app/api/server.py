from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from services import minecraft
from services import monitoring


API_VERSION = "0.1.0"

app = FastAPI(
    title="MineBox API",
    description="Local management API for the MineBox Minecraft server appliance.",
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
)


def minecraft_status() -> dict[str, Any]:
    return {
        "running": minecraft.is_running(),
        "status": minecraft.status_text(),
        "players": minecraft.player_count_text(),
        "version": minecraft.version(),
        "uptime": minecraft.uptime(),
    }


def system_status() -> dict[str, Any]:
    sample = monitoring.sample()

    return {
        "cpu_percent": sample.cpu,
        "memory_percent": sample.memory,
        "minecraft_memory_mb": sample.server_memory_mb,
    }


def run_minecraft_action(
    action: str,
    function: Callable[[], Any],
) -> dict[str, Any]:
    result = function()

    payload = {
        "ok": bool(result.ok),
        "action": action,
        "message": (
            result.stdout
            or result.stderr
            or f"Minecraft {action} command completed."
        ),
        "minecraft": minecraft_status(),
    }

    if not result.ok:
        raise HTTPException(
            status_code=500,
            detail=payload,
        )

    return payload


@app.get(
    "/",
    include_in_schema=False,
)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get(
    "/api/v1/health",
    tags=["System"],
)
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "minebox-api",
        "version": API_VERSION,
    }


@app.get(
    "/api/v1/system",
    tags=["System"],
)
def get_system_status() -> dict[str, Any]:
    return {
        "ok": True,
        "system": system_status(),
    }


@app.get(
    "/api/v1/minecraft",
    tags=["Minecraft"],
)
def get_minecraft_status() -> dict[str, Any]:
    return {
        "ok": True,
        "minecraft": minecraft_status(),
    }


@app.get(
    "/api/v1/status",
    tags=["System"],
)
def get_complete_status() -> dict[str, Any]:
    return {
        "ok": True,
        "system": system_status(),
        "minecraft": minecraft_status(),
    }


@app.post(
    "/api/v1/minecraft/start",
    tags=["Minecraft"],
)
def start_minecraft() -> dict[str, Any]:
    return run_minecraft_action("start", minecraft.start)


@app.post(
    "/api/v1/minecraft/stop",
    tags=["Minecraft"],
)
def stop_minecraft() -> dict[str, Any]:
    return run_minecraft_action("stop", minecraft.stop)


@app.post(
    "/api/v1/minecraft/restart",
    tags=["Minecraft"],
)
def restart_minecraft() -> dict[str, Any]:
    return run_minecraft_action("restart", minecraft.restart)
