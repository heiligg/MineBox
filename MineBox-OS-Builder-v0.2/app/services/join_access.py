from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from services import network
from services import servers
from services.system import CommandResult, run


AVAHI_SERVICE_SOURCE = (
    Path(__file__).resolve().parent / "avahi" / "minebox.service"
)
AVAHI_SERVICE_TARGET = Path("/etc/avahi/services/minebox.service")
UPNP_STATE_FILE = Path("/var/lib/minebox/upnp-mapping.json")


def _hostname() -> str:
    try:
        return socket.gethostname().strip() or "minebox"
    except OSError:
        return "minebox"


def local_hostname() -> str:
    return f"{_hostname()}.local"


def game_port() -> int:
    active = servers.active_server()
    if active is not None:
        return int(active.port)
    props, _error = _read_port_from_properties()
    return props


def _read_port_from_properties() -> tuple[int, str | None]:
    try:
        from services import minecraft

        properties, error = minecraft.read_properties()
        if error:
            return 25565, error
        raw = properties.get("server-port", "25565")
        return int(str(raw).strip()), None
    except (TypeError, ValueError, OSError) as exc:
        return 25565, str(exc)


def lan_ip() -> str | None:
    status = network.status()
    candidates = [
        status.get("ip_address"),
        (status.get("ethernet") or {}).get("ip_address"),
        (status.get("wifi") or {}).get("ip_address"),
    ]
    for address in candidates:
        text = str(address or "").strip()
        if not text:
            continue
        # Never advertise the SoftAP address to home-LAN players.
        if text.startswith("192.168.4."):
            continue
        return text
    return None


def _format_address(host: str, port: int) -> str:
    if port == 25565:
        return host
    return f"{host}:{port}"


def public_ip(timeout: float = 4.0) -> str | None:
    endpoints = (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    )
    for url in endpoints:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                text = response.read().decode("utf-8", errors="replace").strip()
            if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", text):
                return text
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
    return None


def _upnp_binaries() -> list[str]:
    candidates = ["upnpc", "upnpc-static"]
    found: list[str] = []
    for name in candidates:
        result = run(["which", name])
        if result.ok and result.stdout.strip():
            found.append(result.stdout.strip())
    return found


def _load_upnp_state() -> dict[str, Any]:
    try:
        if UPNP_STATE_FILE.is_file():
            data = json.loads(UPNP_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_upnp_state(payload: dict[str, Any]) -> None:
    try:
        UPNP_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = UPNP_STATE_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(UPNP_STATE_FILE)
    except OSError:
        pass


def upnp_status() -> dict[str, Any]:
    binaries = _upnp_binaries()
    state = _load_upnp_state()
    return {
        "tool_available": bool(binaries),
        "mapped": bool(state.get("mapped")),
        "external_ip": state.get("external_ip"),
        "external_port": state.get("external_port"),
        "internal_ip": state.get("internal_ip"),
        "internal_port": state.get("internal_port"),
        "message": state.get("message"),
    }


def enable_upnp(port: int | None = None) -> dict[str, Any]:
    """
    Ask the LAN router to forward the Minecraft TCP port to this MineBox.

    Requires the `upnpc` tool (miniupnpc). If unavailable, returns guidance
    for manual router port forwarding.
    """

    target_port = int(port or game_port())
    internal_ip = lan_ip()
    binaries = _upnp_binaries()

    if not internal_ip:
        payload = {
            "ok": False,
            "mapped": False,
            "message": (
                "MineBox does not have a LAN IP yet. Connect Ethernet or Wi-Fi "
                "first, then try again."
            ),
        }
        _save_upnp_state(payload)
        return payload

    if not binaries:
        payload = {
            "ok": False,
            "mapped": False,
            "message": (
                "Automatic port forwarding is unavailable (upnpc not installed). "
                f"On your router, forward TCP {target_port} to {internal_ip}."
            ),
            "internal_ip": internal_ip,
            "internal_port": target_port,
            "external_port": target_port,
        }
        _save_upnp_state(payload)
        return payload

    binary = binaries[0]
    # Delete any previous mapping for this port, then add a fresh one.
    run(
        [binary, "-d", str(target_port), "tcp"],
        timeout=20,
    )
    result = run(
        [
            binary,
            "-e",
            "MineBox Minecraft",
            "-a",
            internal_ip,
            str(target_port),
            str(target_port),
            "tcp",
            "0",
        ],
        timeout=30,
    )
    external = public_ip()
    if not result.ok:
        payload = {
            "ok": False,
            "mapped": False,
            "message": (
                result.message
                or "The router refused an automatic port forward. "
                f"Forward TCP {target_port} to {internal_ip} manually."
            ),
            "internal_ip": internal_ip,
            "internal_port": target_port,
            "external_port": target_port,
            "external_ip": external,
        }
        _save_upnp_state(payload)
        return payload

    payload = {
        "ok": True,
        "mapped": True,
        "message": (
            f"Router port {target_port} is forwarded to this MineBox. "
            "Friends can join with the internet address below."
        ),
        "internal_ip": internal_ip,
        "internal_port": target_port,
        "external_port": target_port,
        "external_ip": external,
    }
    _save_upnp_state(payload)
    return payload


def disable_upnp(port: int | None = None) -> dict[str, Any]:
    target_port = int(port or game_port())
    binaries = _upnp_binaries()
    if not binaries:
        payload = {
            "ok": True,
            "mapped": False,
            "message": "No automatic port mapping tool is installed.",
        }
        _save_upnp_state(payload)
        return payload

    result = run(
        [binaries[0], "-d", str(target_port), "tcp"],
        timeout=20,
    )
    payload = {
        "ok": bool(result.ok),
        "mapped": False,
        "message": (
            "Automatic port forwarding was removed."
            if result.ok
            else result.message
        ),
        "internal_port": target_port,
        "external_port": target_port,
    }
    _save_upnp_state(payload)
    return payload


def ensure_avahi_advertisement(port: int | None = None) -> CommandResult:
    """Install/update the Avahi service file so LAN clients see MineBox."""
    target_port = int(port or game_port())
    script = Path("/opt/minebox/scripts/minebox_install_avahi.py")
    if not script.is_file():
        script = Path(__file__).resolve().parents[1] / "scripts" / "minebox_install_avahi.py"
    if not script.is_file():
        return CommandResult(
            False,
            stderr="Avahi install script is missing from the MineBox install.",
        )

    helpers = [
        [
            "sudo",
            "-n",
            "/usr/local/sbin/minebox-install-avahi",
            "--port",
            str(target_port),
        ],
        [
            "sudo",
            "-n",
            "/usr/bin/python3",
            str(script),
            "--port",
            str(target_port),
        ],
    ]
    result = CommandResult(False, stderr="Avahi install helper failed.")
    for command in helpers:
        result = run(command, timeout=30)
        if result.ok:
            break

    if not result.ok:
        # Root update apply path can write directly.
        try:
            if not AVAHI_SERVICE_SOURCE.is_file():
                return result
            body = AVAHI_SERVICE_SOURCE.read_text(encoding="utf-8")
            body = re.sub(
                r"(<type>_minecraft\._tcp</type>\s*<port>)\d+(</port>)",
                rf"\g<1>{target_port}\g<2>",
                body,
                count=1,
            )
            AVAHI_SERVICE_TARGET.parent.mkdir(parents=True, exist_ok=True)
            AVAHI_SERVICE_TARGET.write_text(body, encoding="utf-8")
        except OSError as exc:
            return CommandResult(False, stderr=result.stderr or str(exc))

    run(
        [
            "sudo",
            "-n",
            "/usr/bin/systemctl",
            "enable",
            "avahi-daemon.service",
        ],
        timeout=30,
    )
    run(
        [
            "sudo",
            "-n",
            "/usr/bin/systemctl",
            "start",
            "avahi-daemon.service",
        ],
        timeout=30,
    )
    run(
        [
            "sudo",
            "-n",
            "/usr/bin/systemctl",
            "try-reload-or-restart",
            "avahi-daemon.service",
        ],
        timeout=30,
    )
    return CommandResult(True, stdout=f"Advertising Minecraft on port {target_port}.")


def status() -> dict[str, Any]:
    port = game_port()
    host = local_hostname()
    ip_address = lan_ip()
    wan_ip = public_ip()
    mapping = upnp_status()
    mapped = bool(mapping.get("mapped"))

    lan_address = _format_address(host, port)
    lan_ip_address = _format_address(ip_address, port) if ip_address else None
    internet_address = (
        _format_address(wan_ip, mapping.get("external_port") or port)
        if wan_ip
        else None
    )

    return {
        "ok": True,
        "hostname": _hostname(),
        "local_hostname": host,
        "lan_ip": ip_address,
        "game_port": port,
        "lan_address": lan_address,
        "lan_ip_address": lan_ip_address,
        "public_ip": wan_ip,
        "internet_address": internet_address,
        "internet_mapped": mapped,
        "upnp": mapping,
        "notes": [
            f"On the same home Wi‑Fi, open the dashboard at http://{host}/ "
            f"and join Minecraft with {lan_address}"
            + (f" or {lan_ip_address}" if lan_ip_address else "")
            + ".",
            "If minebox.local does not resolve, use the LAN IP shown above.",
            (
                f"Friends on the internet can join {internet_address}."
                if mapped and internet_address
                else (
                    f"For internet friends: forward TCP {port} on your router to "
                    f"{ip_address or 'this MineBox'}"
                    + (f", then share {internet_address}." if internet_address else ".")
                )
            ),
        ],
    }