from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services import network


router = APIRouter(
    prefix="/api/v1/network",
    tags=["network"],
)


class WifiConnectRequest(BaseModel):
    ssid: str = Field(
        ...,
        min_length=1,
        max_length=32,
    )
    password: str | None = Field(
        default=None,
        max_length=64,
    )
    hidden: bool = False


class HotspotStartRequest(BaseModel):
    ssid: str = Field(
        default=network.DEFAULT_HOTSPOT_SSID,
        min_length=1,
        max_length=32,
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=63,
    )


class ForgetWifiRequest(BaseModel):
    connection_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )


def _result_response(result: Any) -> dict[str, Any]:
    """
    Convert a MineBox CommandResult into a JSON response.
    """

    if not result.ok:
        raise HTTPException(
            status_code=400,
            detail=result.message,
        )

    return {
        "ok": True,
        "message": result.message,
    }


@router.get("/status")
def network_status(request: Request) -> dict[str, Any]:
    """
    Centralized network state (roles, hotspot, uplink, sharing, remote-access).
    """

    from networking.state import snapshot

    authenticated = request.session.get("authenticated") is True
    snap = snapshot(authenticated=authenticated, include_legacy=True)
    return {
        "ok": True,
        "network": snap,
    }


@router.get("/roles")
def network_roles() -> dict[str, Any]:
    from networking import roles

    assignment = roles.resolve_roles(persist=False)
    return {"ok": True, "roles": assignment.to_public_dict()}


@router.post("/recovery/retry")
def network_recovery_retry() -> dict[str, Any]:
    from networking import recovery

    return recovery.manual_retry("manual_retry")


@router.get("/support-bundle")
def network_support_bundle() -> dict[str, Any]:
    """Authenticated redacted network diagnostics (also used by support export)."""
    from networking.support_bundle import build_network_support_bundle

    return {"ok": True, "bundle": build_network_support_bundle()}


@router.get("/wifi")
def wifi_scan(
    rescan: bool = Query(default=True),
) -> dict[str, Any]:
    """
    Scan for Wi-Fi networks visible to MineBox.
    """

    result = network.scan_wifi(
        rescan=rescan,
    )

    if not result.get("ok"):
        raise HTTPException(
            status_code=503,
            detail=result.get(
                "message",
                "Wi-Fi scanning is unavailable.",
            ),
        )

    return result


@router.post("/connect")
def wifi_connect(
    request: WifiConnectRequest,
) -> dict[str, Any]:
    """
    Connect MineBox to a selected Wi-Fi network.

    The USB Wi-Fi client adapter is used when the setup hotspot owns wlan0.
    """

    result = network.connect_wifi(
        ssid=request.ssid,
        password=request.password,
        hidden=request.hidden,
    )

    response = _result_response(result)
    response["network"] = network.status()

    return response


@router.post("/disconnect")
def wifi_disconnect() -> dict[str, Any]:
    """
    Disconnect the current Wi-Fi interface.
    """

    result = network.disconnect_wifi()

    response = _result_response(result)
    response["network"] = network.status()

    return response


@router.get("/saved")
def saved_wifi_connections() -> dict[str, Any]:
    """
    List saved Wi-Fi profiles.

    Wi-Fi passwords are never returned.
    """

    connections = network.saved_wifi_connections()

    return {
        "ok": True,
        "connections": connections,
        "count": len(connections),
    }


@router.post("/forget")
def forget_wifi(
    request: ForgetWifiRequest,
) -> dict[str, Any]:
    """
    Delete a saved Wi-Fi connection profile.
    """

    result = network.forget_wifi(
        request.connection_name,
    )

    return _result_response(result)


@router.post("/hotspot/start")
def hotspot_start(
    request: HotspotStartRequest,
) -> dict[str, Any]:
    """
    Start the MineBox setup hotspot.
    """

    result = network.start_hotspot(
        ssid=request.ssid,
        password=request.password,
    )

    response = _result_response(result)
    response["network"] = network.status()

    return response


@router.post("/hotspot/stop")
def hotspot_stop() -> dict[str, Any]:
    """
    Stop the MineBox setup hotspot.
    """

    result = network.stop_hotspot()

    response = _result_response(result)
    response["network"] = network.status()

    return response
