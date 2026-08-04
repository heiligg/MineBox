from typing import Any, Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import minecraft

router = APIRouter(
    prefix="/api/v1/minecraft",
    tags=["Minecraft"],
)


class ConfirmRequest(BaseModel):
    confirm: bool = False


def minecraft_status() -> dict[str, Any]:
    payload = {
        "running": minecraft.is_running(),
        "status": minecraft.status_text(),
        "players": minecraft.player_count_text(),
        "version": minecraft.version(),
        "uptime": minecraft.uptime(),
    }
    try:
        from services.lifecycle import get_lifecycle

        snap = get_lifecycle().snapshot()
        payload["lifecycle"] = snap
        payload["state"] = (snap.get("state") or {}).get("value")
    except Exception:
        pass
    try:
        from services import minecraft_health

        payload["health"] = minecraft_health.collect_health().to_dict()
    except Exception:
        pass
    return payload


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
def stop(body: ConfirmRequest | None = None):
    if not body or not body.confirm:
        raise HTTPException(status_code=400, detail="Stop requires confirm=true.")
    return run_action("stop", minecraft.stop)


@router.post("/restart")
def restart(body: ConfirmRequest | None = None):
    if not body or not body.confirm:
        raise HTTPException(status_code=400, detail="Restart requires confirm=true.")
    return run_action("restart", minecraft.restart)


@router.post("/recover")
def recover(body: ConfirmRequest | None = None):
    if not body or not body.confirm:
        raise HTTPException(status_code=400, detail="Recover requires confirm=true.")
    from services.lifecycle import get_lifecycle

    return run_action("recover", get_lifecycle().recover)


# MineBox Server Settings Routes v1

@router.get("/launch-debug")
def launch_debug() -> dict[str, Any]:
    """Return the resolved launch command and recent crash logs for support."""
    from services import servers
    from services.launcher import build_command

    active = servers.active_server()
    payload: dict[str, Any] = {
        "ok": True,
        "active_server": active.__dict__ if active else None,
    }
    try:
        server_dir, command, _env = build_command()
        payload["server_dir"] = str(server_dir)
        payload["command"] = command
    except Exception as error:
        payload["ok"] = False
        payload["build_error"] = str(error)

    if active is not None:
        server_dir = Path(active.directory)
        for name in (
            "minebox-stderr.log",
            "minebox-launcher.log",
            "latest.log",
            "fml-server-latest.log",
            "debug.log",
        ):
            path = server_dir / "logs" / name
            if not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            payload[name] = lines[-80:]

    return payload


@router.get("/settings")
def server_settings():
    result = minecraft.read_server_settings()

    if not result.get("ok"):
        raise HTTPException(
            status_code=500,
            detail=result,
        )

    return result


@router.put("/settings")
def update_server_settings(
    payload: dict[str, Any],
):
    result = minecraft.save_server_settings(payload)

    if not result.get("ok"):
        raise HTTPException(
            status_code=result.get("status_code", 400),
            detail=result,
        )

    return result


@router.post("/settings")
def update_server_settings_post(
    payload: dict[str, Any],
):
    """Allow POST as well as PUT for broader client compatibility."""
    return update_server_settings(payload)

