"""Centralized network-state service for web, display, diagnostics, setup."""

from __future__ import annotations

import logging
import os
import time
from enum import Enum
from pathlib import Path
from typing import Any

from networking import firewall, recovery, remote_access, roles

LOGGER = logging.getLogger("minebox.network.state")


class NetState(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    DETECTING = "DETECTING"
    CONFIGURING = "CONFIGURING"
    UP = "UP"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    ERROR = "ERROR"


def _lease_clients(lease_file: Path | None = None) -> list[dict[str, str]]:
    path = lease_file or Path(
        os.environ.get("MINEBOX_DNSMASQ_LEASES", "/var/lib/misc/dnsmasq.leases")
    )
    if not path.is_file():
        # Alternate common path
        alt = Path("/var/lib/dnsmasq/dnsmasq.leases")
        path = alt if alt.is_file() else path
    if not path.is_file():
        return []
    clients: list[dict[str, str]] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            clients.append(
                {
                    "expires": parts[0],
                    "mac": parts[1],
                    "ip": parts[2],
                    "hostname": parts[3] if parts[3] != "*" else "",
                }
            )
    except OSError:
        return []
    return clients


def _unit_active(unit: str) -> bool:
    try:
        from services.system import run

        result = run(["systemctl", "is-active", unit], timeout=5)
        return result.ok and result.stdout.strip() == "active"
    except Exception:
        return False


def _connectivity_probe() -> dict[str, Any]:
    """Bounded low-frequency internet/DNS check — not 'has IP'."""
    # Use cached result in module for rate limiting.
    now = time.time()
    cache = getattr(_connectivity_probe, "_cache", None)
    if cache and now - cache["at"] < 30:
        return cache["data"]

    internet = False
    dns_ok = False
    reason = "not_checked"
    try:
        import socket

        # DNS reachability (system resolver)
        socket.getaddrinfo("example.com", 80, proto=socket.IPPROTO_TCP)
        dns_ok = True
        # TCP connect with short timeout to a well-known IP (no dependency on DNS for this part)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        try:
            sock.connect(("1.1.1.1", 443))
            internet = True
            reason = "ok"
        finally:
            sock.close()
    except OSError as exc:
        reason = type(exc).__name__
        if dns_ok and not internet:
            reason = "dns_ok_no_tcp"
        elif not dns_ok:
            reason = "dns_or_network_unavailable"

    data = {
        "internet_reachable": internet,
        "dns_reachable": dns_ok,
        "reason": reason,
        "checked_at": now,
    }
    _connectivity_probe._cache = {"at": now, "data": data}  # type: ignore[attr-defined]
    return data


def _hostapd_ssid() -> str | None:
    for path in (
        Path("/etc/hostapd/hostapd.conf"),
        Path("/opt/minebox/services/hotspot/hostapd.conf"),
    ):
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("ssid="):
                    return line.split("=", 1)[1].strip() or None
        except OSError:
            continue
    try:
        from core.minebox_config import get_config

        return get_config().hotspot_ssid
    except Exception:
        return "MineBox-Setup"


def snapshot(*, authenticated: bool = False, include_legacy: bool = True) -> dict[str, Any]:
    """Full network state for APIs/UIs. Never includes hotspot PSK or auth keys."""
    assignment = roles.resolve_roles(persist=True)
    probe = _connectivity_probe()

    # Determine active uplink preference: Ethernet then Wi-Fi.
    active_uplink = None
    uplink_order = []
    try:
        from services import network as network_service

        eth = network_service.ethernet_interface()
        wifi_client = network_service.client_wifi_interface()
        # Prefer role-resolved names when present.
        eth = assignment.ethernet_uplink or eth
        wifi_client = assignment.wifi_uplink or wifi_client

        eth_addrs = network_service._ip_ipv4(eth) if eth else []  # noqa: SLF001
        wifi_addrs = network_service._ip_ipv4(wifi_client) if wifi_client else []  # noqa: SLF001
        eth_up = bool(eth_addrs) and not any(a.startswith("169.254.") for a in eth_addrs)
        wifi_up = bool(wifi_addrs) and not any(a.startswith("169.254.") for a in wifi_addrs)

        if eth_up:
            active_uplink = eth
            uplink_order.append("ethernet")
        if wifi_up:
            uplink_order.append("wifi")
            if not active_uplink:
                active_uplink = wifi_client
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("uplink detect failed: %s", exc)

    roles.set_active_uplink(assignment, active_uplink)

    hotspot_iface = assignment.hotspot
    hostapd_up = _unit_active("hostapd.service")
    dnsmasq_up = _unit_active("dnsmasq.service")
    hotspot_state = NetState.DOWN.value
    if hostapd_up and dnsmasq_up:
        hotspot_state = NetState.UP.value
    elif hostapd_up or dnsmasq_up:
        hotspot_state = NetState.DEGRADED.value
    elif assignment.unresolved:
        hotspot_state = NetState.ERROR.value
    elif not hotspot_iface:
        hotspot_state = NetState.UNAVAILABLE.value

    clients = _lease_clients()
    policy = firewall.build_policy_for_roles(hotspot_iface, has_uplink=bool(active_uplink))

    remote = remote_access.get_remote_access_provider().status(authenticated=authenticated)

    ethernet_state = NetState.UP.value if active_uplink and active_uplink == assignment.ethernet_uplink else NetState.DOWN.value
    wifi_uplink_state = NetState.UP.value if active_uplink and active_uplink == assignment.wifi_uplink else NetState.DOWN.value
    if assignment.ethernet_uplink and ethernet_state == NetState.DOWN.value:
        ethernet_state = NetState.DOWN.value
    if not assignment.wifi_uplink:
        wifi_uplink_state = NetState.UNAVAILABLE.value

    internet_state = NetState.UP.value if probe["internet_reachable"] else NetState.DOWN.value
    if active_uplink and not probe["internet_reachable"]:
        internet_state = NetState.DEGRADED.value  # has uplink IP path but no internet

    sharing_state = (
        NetState.UP.value
        if policy["internet_sharing_active"]
        else (
            NetState.DISABLED.value
            if not policy["internet_sharing_configured"]
            else NetState.DOWN.value
        )
    )
    # NetState has no DISABLED — use string for sharing.
    if not policy["internet_sharing_configured"]:
        sharing_state = "DISABLED"
    elif policy["internet_sharing_active"]:
        sharing_state = NetState.UP.value
    else:
        sharing_state = NetState.DOWN.value

    firewall_health = (
        NetState.UP.value
        if policy["validation"].get("ok")
        else NetState.ERROR.value
    )

    payload: dict[str, Any] = {
        "ok": True,
        "roles": assignment.to_public_dict(),
        "hotspot": {
            "state": hotspot_state,
            "iface": hotspot_iface,
            "ssid": _hostapd_ssid(),
            "ip": "192.168.4.1",
            "subnet": "192.168.4.0/24",
            "hostapd": hostapd_up,
            "dnsmasq": dnsmasq_up,
            "clients": clients,
            "client_count": len(clients),
        },
        "ethernet": {
            "state": ethernet_state,
            "iface": assignment.ethernet_uplink,
        },
        "wifi_uplink": {
            "state": wifi_uplink_state,
            "iface": assignment.wifi_uplink,
        },
        "active_uplink": active_uplink,
        "uplink_priority": ["ethernet", "wifi"],
        "internet": {
            "state": internet_state,
            **probe,
        },
        "internet_sharing": {
            "state": sharing_state,
            "configured": policy["internet_sharing_configured"],
            "active": policy["internet_sharing_active"],
        },
        "firewall": {
            "state": firewall_health,
            "validation": {
                "ok": policy["validation"].get("ok"),
                "errors": policy["validation"].get("errors"),
                "warnings": policy["validation"].get("warnings"),
                "has_nat": policy["validation"].get("has_nat"),
            },
        },
        "remote_access": remote.to_public_dict(authenticated=authenticated),
        "recovery": recovery.status(),
        "unresolved": assignment.unresolved,
        "warnings": assignment.warnings,
        "local_only": active_uplink is None,
        "last_error": recovery.status().get("last_error"),
    }

    # Never expose secrets.
    for key in ("password", "psk", "passphrase", "auth_key", "authkey"):
        payload.pop(key, None)

    if include_legacy:
        try:
            from services import network as network_service

            legacy = network_service.status()
            # Merge useful flat fields for existing dashboard JS.
            payload["legacy"] = {
                k: legacy.get(k)
                for k in (
                    "connected",
                    "connection_type",
                    "ip_address",
                    "gateway",
                    "dns",
                    "interface",
                    "ssid",
                    "hotspot_active",
                    "wifi_hardware_available",
                )
                if k in legacy
            }
            # Keep backward-compatible top-level keys expected by network.js / display.
            payload.update(
                {
                    "hotspot_ssid": payload["hotspot"]["ssid"],
                    "hotspot_address": payload["hotspot"]["ip"],
                    "hotspot_clients": payload["hotspot"]["client_count"],
                    "ethernet_status": payload["ethernet"]["state"],
                    "wifi_status": payload["wifi_uplink"]["state"],
                    "internet_status": payload["internet"]["state"],
                    "internet_sharing_active": payload["internet_sharing"]["active"],
                    "remote_access_state": payload["remote_access"].get("state"),
                    "remote_minecraft_exposed": bool(
                        payload["remote_access"].get("expose_minecraft")
                    ),
                    "ip": legacy.get("ip_address"),
                    "local_ip": legacy.get("ip_address"),
                }
            )
            # Nested objects used by setup wizard.
            if "ethernet" in legacy:
                payload["ethernet"] = {**payload["ethernet"], **legacy.get("ethernet", {})}
            if "wifi" in legacy:
                payload["wifi"] = legacy.get("wifi")
            if "hotspot" in legacy and isinstance(legacy.get("hotspot"), dict):
                payload["hotspot"] = {**payload["hotspot"], **legacy["hotspot"]}
                payload["hotspot"]["state"] = hotspot_state
                payload["hotspot"]["clients"] = clients
                payload["hotspot"]["client_count"] = len(clients)
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("legacy status merge failed: %s", exc)

    return payload


def apply_firewall_policy() -> dict[str, Any]:
    """Generate and optionally write nftables policy (no root apply in CI)."""
    assignment = roles.resolve_roles(persist=False)
    snap = snapshot(authenticated=False, include_legacy=False)
    has_uplink = bool(snap.get("active_uplink"))
    policy = firewall.build_policy_for_roles(assignment.hotspot, has_uplink=has_uplink)
    written = None
    if os.environ.get("MINEBOX_WRITE_NFT", "").strip() in {"1", "true", "yes"}:
        path = Path(os.environ.get("MINEBOX_NFT_FILE", "/tmp/minebox-nftables.conf"))
        written = str(firewall.write_nftables_file(policy["ruleset"], path))
    return {
        "ok": policy["validation"]["ok"],
        "written": written,
        "internet_sharing_active": policy["internet_sharing_active"],
        "validation": policy["validation"],
    }
