"""Local display (800×480 kiosk) API — loopback-scoped actions."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from pathlib import Path

from display.actions import (
    ALLOWED_DISPLAY_ACTIONS,
    DESTRUCTIVE_ACTIONS,
    resolve_action_map,
)
from display.bridge import get_display_bridge
from display.events import DisplayEventType
from display.local_trust import (
    DISPLAY_COOKIE,
    DISPLAY_TOKEN_HEADER,
    client_is_loopback,
    ensure_display_token,
    public_trust_info,
    verify_display_token,
)

LOGGER = logging.getLogger("minebox.display")

router = APIRouter(tags=["Display"])
APP_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(APP_DIR / "web" / "templates"))


class InjectEventRequest(BaseModel):
    type: str = Field(min_length=3, max_length=64)


class DisplayActionRequest(BaseModel):
    action: str = Field(min_length=3, max_length=64)
    confirm: bool = False


def _client_host(request: Request) -> str | None:
    if request.client:
        return request.client.host
    return None


def _display_authorized(request: Request) -> bool:
    if not client_is_loopback(_client_host(request)):
        return False
    header = request.headers.get(DISPLAY_TOKEN_HEADER)
    cookie = request.cookies.get(DISPLAY_COOKIE)
    return verify_display_token(header) or verify_display_token(cookie)


def require_display_trust(request: Request) -> None:
    if not _display_authorized(request):
        raise HTTPException(
            status_code=403,
            detail="Local display authorization required (loopback + display token).",
        )


@router.get("/display", response_class=HTMLResponse, include_in_schema=False)
def display_home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="display.html",
        context={"width": 800, "height": 480},
    )


@router.get("/display/dev", response_class=HTMLResponse, include_in_schema=False)
def display_dev(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="display.html",
        context={"width": 800, "height": 480, "dev_mode": True},
    )


@router.post("/api/v1/display/session")
def display_session(request: Request, response: Response) -> dict[str, Any]:
    """Issue display cookie — loopback only. Token from header or auto-issue on loopback bootstrap."""
    if not client_is_loopback(_client_host(request)):
        raise HTTPException(status_code=403, detail="Display session is loopback-only.")

    header = request.headers.get(DISPLAY_TOKEN_HEADER)
    token = ensure_display_token()
    if header and not verify_display_token(header):
        raise HTTPException(status_code=403, detail="Invalid display token.")
    # Loopback without header: bind cookie to the on-disk token (systemd kiosk).
    if header and verify_display_token(header):
        token = header.strip()

    response.set_cookie(
        key=DISPLAY_COOKIE,
        value=token,
        httponly=True,
        samesite="strict",
        max_age=60 * 60 * 24 * 30,
        path="/",
    )
    return {"ok": True, "trust": public_trust_info()}


@router.get("/api/v1/display/trust")
def display_trust(request: Request) -> dict[str, Any]:
    return {
        "ok": True,
        "loopback": client_is_loopback(_client_host(request)),
        "authorized": _display_authorized(request),
        **public_trust_info(),
    }


def _current_action_map():
    bridge = get_display_bridge()
    return resolve_action_map(encoder_available=bridge.encoder_connected)


@router.get("/api/v1/display/action-map")
def action_map() -> dict[str, Any]:
    bridge = get_display_bridge()
    amap = resolve_action_map(encoder_available=bridge.encoder_connected)
    return {
        "ok": True,
        "map": amap.to_public_dict(),
        "encoder_connected": bridge.encoder_connected,
    }


@router.get("/api/v1/display/snapshot")
def snapshot(request: Request) -> dict[str, Any]:
    """Aggregated status for the kiosk. Secrets never included."""
    from core.state_service import get_state_service
    from services import first_boot

    stale = False
    fetched_at = time.time()
    try:
        foundation = get_state_service().public_status()
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("display snapshot foundation failed: %s", exc)
        foundation = {"ok": False, "error": "backend_unavailable"}
        stale = True

    setup_complete = False
    try:
        setup_complete = bool(first_boot.is_appliance_setup_complete())
    except Exception:
        setup_complete = False

    backups: dict[str, Any] = {}
    try:
        from services import backups as backup_service

        status = backup_service.backup_status()
        items = status.get("backups") or []
        total_size = sum(int(i.get("size_bytes") or 0) for i in items)
        latest = items[0] if items else None
        backups = {
            "count": status.get("backup_count", len(items)),
            "total_size": total_size,
            "busy": status.get("busy"),
            "latest": {
                "filename": (latest or {}).get("filename"),
                "size": (latest or {}).get("size_bytes")
                or (latest or {}).get("size"),
                "created_at": (latest or {}).get("created_at"),
            }
            if latest
            else None,
        }
    except Exception:
        backups = {"count": 0, "error": "unavailable"}

    network: dict[str, Any] = {}
    try:
        from networking.state import snapshot

        raw = snapshot(authenticated=False, include_legacy=True)
        network = _sanitize_network(raw)
    except Exception:
        try:
            from core.minebox_config import get_config

            cfg = get_config()
            network = {
                "hotspot_ssid": cfg.hotspot_ssid,
                "hotspot_address": "192.168.4.1",
                "remote_access_state": "DISABLED",
            }
        except Exception:
            network = {"remote_access_state": "DISABLED"}

    return {
        "ok": not stale,
        "stale": stale,
        "fetched_at": fetched_at,
        "setup_complete": setup_complete,
        "foundation": foundation,
        "backups": backups,
        "network": network,
        "action_map": resolve_action_map(
            encoder_available=get_display_bridge().encoder_connected
        ).to_public_dict(),
        "hardware_diag": get_display_bridge().diagnostic_live(),
    }


@router.get("/api/v1/display/events")
def poll_events(request: Request, diagnostics: bool = False) -> dict[str, Any]:
    """Poll HAL-derived display events. Diagnostics mode suppresses action side-effects client-side."""
    bridge = get_display_bridge()
    bridge.set_diagnostics_mode(diagnostics)
    events = [e.to_dict() for e in bridge.poll()]
    return {
        "ok": True,
        "events": events,
        "diagnostics_mode": bridge.diagnostics_mode,
        "map": resolve_action_map(encoder_available=bridge.encoder_connected).to_public_dict(),
    }


@router.post("/api/v1/display/events/inject")
def inject_event(request: Request, body: InjectEventRequest) -> dict[str, Any]:
    """Dev/test injection — loopback + display trust only."""
    require_display_trust(request)
    try:
        event_type = DisplayEventType(body.type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown event type.") from exc
    event = get_display_bridge().inject(event_type, source="api")
    return {"ok": True, "event": event.to_dict()}


@router.post("/api/v1/display/action")
def display_action(request: Request, body: DisplayActionRequest) -> dict[str, Any]:
    require_display_trust(request)
    action = body.action.strip()
    if action not in ALLOWED_DISPLAY_ACTIONS:
        raise HTTPException(status_code=400, detail="Action not allowed for local display.")
    if action in DESTRUCTIVE_ACTIONS and not body.confirm:
        raise HTTPException(status_code=400, detail=f"{action} requires confirm=true.")

    # Setup gating: block control until first-boot complete.
    try:
        from services import first_boot

        if not first_boot.is_appliance_setup_complete() and action in ALLOWED_DISPLAY_ACTIONS:
            raise HTTPException(
                status_code=403,
                detail="First-boot setup incomplete.",
            )
    except HTTPException:
        raise
    except Exception:
        pass

    try:
        result = _execute_display_action(action)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("display action %s failed: %s", action, exc)
        detail = str(exc).strip() or "Display action failed."
        # Prefer concrete backup/lifecycle errors over a generic 500.
        if "Backup" in type(exc).__name__ or action.startswith("backup_"):
            raise HTTPException(status_code=400, detail=detail) from exc
        raise HTTPException(status_code=500, detail=detail) from exc

    return {"ok": True, "action": action, "result": result}


def _sanitize_network(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep display-safe network fields; never return PSK/passwords."""
    blocked = ("password", "psk", "secret", "token", "passphrase", "key")
    safe: dict[str, Any] = {}
    for key, value in raw.items():
        lowered = str(key).lower()
        if any(b in lowered for b in blocked):
            continue
        if isinstance(value, dict):
            safe[key] = _sanitize_network(value)
        else:
            safe[key] = value
    if "remote_access" not in safe:
        safe["remote_access"] = "disabled"
    return safe


def _execute_display_action(action: str) -> dict[str, Any]:
    if action == "server_start":
        from services import minecraft

        r = minecraft.start()
        return {"ok": r.ok, "message": r.stdout or r.stderr}
    if action == "server_stop":
        from services import minecraft

        r = minecraft.stop()
        return {"ok": r.ok, "message": r.stdout or r.stderr}
    if action == "server_restart":
        from services import minecraft

        r = minecraft.restart()
        return {"ok": r.ok, "message": r.stdout or r.stderr}
    if action == "backup_create":
        from services import backups

        created = backups.create_backup()
        if isinstance(created, dict):
            name = created.get("filename") or created.get("path") or created
            return {
                "ok": True,
                "backup": name,
                "message": f"Backup created: {name}",
            }
        return {"ok": True, "backup": str(created), "message": f"Backup created: {created}"}
    if action == "services_restart":
        import subprocess

        result = subprocess.run(
            ["sudo", "-n", "/usr/bin/systemctl", "restart", "minebox-api.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "ok": result.returncode == 0,
            "message": "MineBox API restart requested."
            if result.returncode == 0
            else (result.stderr or "restart failed"),
        }
    if action == "device_reboot":
        from services.safe_shutdown import request_shutdown

        return request_shutdown(reason="display", reboot=True)
    if action == "device_shutdown":
        from services.safe_shutdown import request_shutdown

        return request_shutdown(reason="display", reboot=False)
    raise HTTPException(status_code=400, detail="Unknown action.")
