from __future__ import annotations

import ipaddress
import json
import re
import shutil
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


VOICECHAT_UDP_PORT = 24454


def _private_ip(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        return ipaddress.ip_address(text).is_private
    except ValueError:
        return False


def _upnp_binaries() -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for name in ("upnpc", "upnpc-static"):
        path = shutil.which(name)
        candidates = [path] if path else []
        candidates.extend((f"/usr/bin/{name}", f"/usr/sbin/{name}"))
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            if Path(candidate).is_file():
                found.append(candidate)
                seen.add(candidate)
    return found


def _upnp_run(binary: str, lan_ip: str, args: list[str], timeout: int = 30) -> CommandResult:
    command = [binary]
    if lan_ip:
        command.extend(["-m", lan_ip])
    command.extend(args)
    return run(command, timeout=timeout)


def _parse_upnp_external_ip(text: str) -> str | None:
    match = re.search(
        r"ExternalIPAddress\s*=\s*(\d{1,3}(?:\.\d{1,3}){3})",
        text or "",
    )
    if match:
        return match.group(1)
    match = re.search(
        r"external\s+(\d{1,3}(?:\.\d{1,3}){3}):\d+",
        text or "",
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def _upnp_succeeded(result: CommandResult) -> bool:
    blob = f"{result.stdout}\n{result.stderr}"
    if "No IGD UPnP Device found" in blob:
        return False
    if "is redirected to" in blob or "already redirected" in blob.lower():
        return True
    return bool(result.ok) and "No IGD" not in blob


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
        "double_nat": bool(state.get("double_nat")),
        "internet_reachable": bool(state.get("internet_reachable")),
        "external_ip": state.get("external_ip"),
        "external_port": state.get("external_port"),
        "internal_ip": state.get("internal_ip"),
        "internal_port": state.get("internal_port"),
        "voice_mapped": bool(state.get("voice_mapped")),
        "message": state.get("message"),
    }


def enable_upnp(port: int | None = None) -> dict[str, Any]:
    """
    Ask the LAN router to forward the Minecraft TCP port (and voice-chat UDP)
    to this MineBox via UPnP IGD.
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
                f"On your router, forward TCP {target_port} and UDP "
                f"{VOICECHAT_UDP_PORT} to {internal_ip}."
            ),
            "internal_ip": internal_ip,
            "internal_port": target_port,
            "external_port": target_port,
        }
        _save_upnp_state(payload)
        return payload

    binary = binaries[0]
    # Bind discovery to the home LAN, not the 192.168.4.1 hotspot.
    _upnp_run(binary, internal_ip, ["-d", str(target_port), "tcp"], timeout=20)
    _upnp_run(binary, internal_ip, ["-d", str(VOICECHAT_UDP_PORT), "udp"], timeout=20)
    result = _upnp_run(
        binary,
        internal_ip,
        [
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
    voice = _upnp_run(
        binary,
        internal_ip,
        [
            "-e",
            "MineBox Voice Chat",
            "-a",
            internal_ip,
            str(VOICECHAT_UDP_PORT),
            str(VOICECHAT_UDP_PORT),
            "udp",
            "0",
        ],
        timeout=30,
    )
    combined = f"{result.stdout}\n{result.stderr}\n{voice.stdout}\n{voice.stderr}"
    igd_ip = _parse_upnp_external_ip(combined)
    wan_ip = public_ip()
    if not _upnp_succeeded(result):
        payload = {
            "ok": False,
            "mapped": False,
            "message": (
                "No UPnP router was found, or it refused the mapping. "
                f"On your router, forward TCP {target_port} "
                f"(and UDP {VOICECHAT_UDP_PORT} for voice chat) to {internal_ip}."
            ),
            "internal_ip": internal_ip,
            "internal_port": target_port,
            "external_port": target_port,
            "external_ip": igd_ip or wan_ip,
            "detail": (result.stderr or result.stdout or "")[:400],
        }
        _save_upnp_state(payload)
        return payload

    double_nat = _private_ip(igd_ip)
    if double_nat:
        message = (
            f"Your Wi-Fi router forwarded TCP {target_port} to this MineBox, "
            f"but that router’s WAN address is {igd_ip} (another router in front). "
            "Internet friends still cannot join until the outer modem/router also "
            f"forwards TCP {target_port} to {internal_ip}, or the mesh is put in "
            "bridge mode."
        )
    else:
        join_host = igd_ip or wan_ip
        message = (
            f"Router port {target_port} is forwarded to this MineBox."
            + (
                f" Friends can join with {join_host}:{target_port}."
                if join_host
                else ""
            )
        )
    payload = {
        "ok": True,
        "mapped": True,
        "double_nat": double_nat,
        "internet_reachable": bool(igd_ip) and not double_nat,
        "message": message,
        "internal_ip": internal_ip,
        "internal_port": target_port,
        "external_port": target_port,
        "external_ip": igd_ip or wan_ip,
        "voice_mapped": _upnp_succeeded(voice),
        "voice_port": VOICECHAT_UDP_PORT,
    }
    _save_upnp_state(payload)
    return payload


def disable_upnp(port: int | None = None) -> dict[str, Any]:
    target_port = int(port or game_port())
    internal_ip = lan_ip() or ""
    binaries = _upnp_binaries()
    if not binaries:
        payload = {
            "ok": True,
            "mapped": False,
            "message": "No automatic port mapping tool is installed.",
        }
        _save_upnp_state(payload)
        return payload

    tcp = _upnp_run(binaries[0], internal_ip, ["-d", str(target_port), "tcp"], timeout=20)
    udp = _upnp_run(
        binaries[0],
        internal_ip,
        ["-d", str(VOICECHAT_UDP_PORT), "udp"],
        timeout=20,
    )
    ok = bool(tcp.ok or udp.ok or "No IGD" not in f"{tcp.stdout}{tcp.stderr}")
    payload = {
        "ok": ok,
        "mapped": False,
        "message": (
            "Automatic port forwarding was removed."
            if ok
            else (tcp.message or udp.message)
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
    reachable = bool(mapping.get("internet_reachable"))
    igd_ip = str(mapping.get("external_ip") or "").strip() or None

    lan_address = _format_address(host, port)
    lan_ip_address = _format_address(ip_address, port) if ip_address else None
    dns: dict[str, Any] = {}
    try:
        from services import public_dns

        dns = public_dns.status()
    except Exception:
        dns = {}
    dns_host = str(dns.get("hostname") or "").strip() or None
    if not dns.get("configured"):
        dns_host = None

    join_host = igd_ip if (mapped and igd_ip and not _private_ip(igd_ip)) else wan_ip
    internet_address = (
        _format_address(dns_host or join_host, mapping.get("external_port") or port)
        if (dns_host or join_host)
        else None
    )

    if mapped and reachable and internet_address:
        internet_note = f"Friends on the internet can join {internet_address}."
    elif mapped and mapping.get("double_nat"):
        internet_note = mapping.get("message") or (
            "The home router accepted UPnP, but another router is in front of it "
            "(double NAT). Internet join still needs a forward on the outer modem."
        )
    else:
        internet_note = (
            f"For internet friends: use Enable internet join, or forward TCP {port} "
            f"on your router to {ip_address or 'this MineBox'}"
            + (f", then share {internet_address}." if internet_address else ".")
        )

    payload = {
        "ok": True,
        "hostname": _hostname(),
        "local_hostname": host,
        "lan_ip": ip_address,
        "game_port": port,
        "lan_address": lan_address,
        "lan_ip_address": lan_ip_address,
        "public_ip": wan_ip,
        "internet_address": internet_address,
        "public_dns": dns,
        "internet_mapped": mapped,
        "internet_reachable": reachable,
        "upnp": mapping,
        "notes": [
            f"On the same home Wi-Fi, open the dashboard at http://{host}/ "
            f"and join Minecraft with {lan_address}"
            + (f" or {lan_ip_address}" if lan_ip_address else "")
            + ".",
            "If minebox.local does not resolve, use the LAN IP shown above.",
            internet_note,
        ],
    }
    if dns_host:
        payload["notes"].append(
            f"Public MineBox name: {dns_host}. Internet friends type that "
            "instead of a raw IP. Port forwarding is still required."
        )
    return payload