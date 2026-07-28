from __future__ import annotations

import re
import socket
from pathlib import Path
from typing import Any

from services.system import CommandResult, run


HOTSPOT_CONNECTION_NAME = "MineBox-Hotspot"
DEFAULT_HOTSPOT_SSID = "MineBox-Setup"
DEFAULT_HOTSPOT_ADDRESS = "192.168.4.1/24"
# Dedicated hostapd AP always owns the onboard radio.
HOTSPOT_INTERFACE = "wlan0"


def _nmcli(arguments: list[str], timeout: int = 30) -> CommandResult:
    """
    Run NetworkManager's nmcli command without using a shell.
    """

    return run(
        [
            "nmcli",
            "--colors",
            "no",
            *arguments,
        ],
        timeout=timeout,
    )


def networkmanager_available() -> bool:
    """
    Return True when nmcli exists and NetworkManager responds.
    """

    result = _nmcli(["general", "status"])

    return result.ok


def _split_nmcli_line(line: str) -> list[str]:
    """
    Split nmcli terse output while preserving escaped colons.

    Example:
        My\\:WiFi:82
    becomes:
        ["My:WiFi", "82"]
    """

    fields: list[str] = []
    current: list[str] = []
    escaped = False

    for character in line:
        if escaped:
            current.append(character)
            escaped = False
            continue

        if character == "\\":
            escaped = True
            continue

        if character == ":":
            fields.append("".join(current))
            current = []
            continue

        current.append(character)

    if escaped:
        current.append("\\")

    fields.append("".join(current))

    return fields


def _wifi_devices() -> list[dict[str, str]]:
    """
    Return Wi-Fi devices known to NetworkManager.
    """

    result = _nmcli(
        [
            "--terse",
            "--fields",
            "DEVICE,TYPE,STATE,CONNECTION",
            "device",
            "status",
        ]
    )

    if not result.ok:
        return []

    devices: list[dict[str, str]] = []

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        fields = _split_nmcli_line(line)

        while len(fields) < 4:
            fields.append("")

        device, device_type, state, connection = fields[:4]

        if device_type != "wifi":
            continue

        devices.append(
            {
                "device": device,
                "type": device_type,
                "state": state,
                "connection": connection,
            }
        )

    return devices


def wifi_interface() -> str | None:
    """
    Return the preferred Wi-Fi interface.

    A connected interface is preferred. Otherwise, return the first
    available Wi-Fi device, including adapters NetworkManager does not manage.
    """

    devices = _wifi_devices()

    for device in devices:
        if device["state"] in {
            "connected",
            "connecting",
        }:
            return device["device"]

    if devices:
        return devices[0]["device"]

    physical = _physical_wifi_interfaces()
    return physical[0] if physical else None


def client_wifi_interface() -> str | None:
    """
    Return a Wi-Fi interface suitable for client scan/join.

    Prefer NetworkManager-managed adapters that are not the dedicated
    setup-hotspot radio (wlan0). Falls back to any NM Wi-Fi device.
    """

    devices = _wifi_devices()
    clients = [
        device
        for device in devices
        if device["device"] != HOTSPOT_INTERFACE
    ]

    for device in clients:
        if device["state"] in {"connected", "connecting"}:
            return device["device"]

    if clients:
        return clients[0]["device"]

    for device in devices:
        if device["state"] in {"connected", "connecting"}:
            return device["device"]

    if devices:
        return devices[0]["device"]

    physical = [
        name
        for name in _physical_wifi_interfaces()
        if name != HOTSPOT_INTERFACE
    ]
    if physical:
        return physical[0]
    return None


def hotspot_radio_in_use() -> bool:
    """True when the onboard AP radio is busy with the setup hotspot."""
    return hotspot_is_active() or _hostapd_hotspot_active()


def _physical_wifi_interfaces() -> list[str]:
    """Return Wi-Fi interface names from sysfs (works even when unmanaged)."""
    net = Path("/sys/class/net")
    if not net.is_dir():
        return []
    interfaces: list[str] = []
    try:
        for entry in sorted(net.iterdir()):
            if (entry / "wireless").is_dir() or (entry / "phy80211").exists():
                interfaces.append(entry.name)
    except OSError:
        return []
    return interfaces


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "minebox"


def _device_ipv4(interface: str) -> list[str]:
    result = _nmcli(
        [
            "--get-values",
            "IP4.ADDRESS",
            "device",
            "show",
            interface,
        ]
    )

    if not result.ok:
        return []

    addresses: list[str] = []

    for raw_line in result.stdout.splitlines():
        address = raw_line.strip()

        if address:
            addresses.append(address)

    return addresses


def _device_gateway(interface: str) -> str | None:
    result = _nmcli(
        [
            "--get-values",
            "IP4.GATEWAY",
            "device",
            "show",
            interface,
        ]
    )

    if not result.ok:
        return None

    for raw_line in result.stdout.splitlines():
        gateway = raw_line.strip()

        if gateway:
            return gateway

    return None


def _device_dns(interface: str) -> list[str]:
    result = _nmcli(
        [
            "--get-values",
            "IP4.DNS",
            "device",
            "show",
            interface,
        ]
    )

    if not result.ok:
        return []

    servers: list[str] = []

    for raw_line in result.stdout.splitlines():
        server = raw_line.strip()

        if server and server not in servers:
            servers.append(server)

    return servers


def _active_wifi_details(
    interface: str,
) -> dict[str, Any] | None:
    result = _nmcli(
        [
            "--terse",
            "--fields",
            "IN-USE,SSID,SIGNAL,SECURITY,FREQ,RATE",
            "device",
            "wifi",
            "list",
            "ifname",
            interface,
        ],
        timeout=20,
    )

    if not result.ok:
        return None

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        fields = _split_nmcli_line(line)

        while len(fields) < 6:
            fields.append("")

        in_use, ssid, signal, security, frequency, rate = fields[:6]

        if in_use not in {"*", "yes"}:
            continue

        try:
            signal_value = int(signal)
        except ValueError:
            signal_value = 0

        return {
            "ssid": ssid,
            "signal": signal_value,
            "security": security or "Open",
            "frequency": frequency,
            "rate": rate,
        }

    return None


def hotspot_is_active() -> bool:
    result = _nmcli(
        [
            "--terse",
            "--fields",
            "NAME,TYPE",
            "connection",
            "show",
            "--active",
        ]
    )

    if not result.ok:
        return False

    for raw_line in result.stdout.splitlines():
        fields = _split_nmcli_line(raw_line.strip())

        if not fields:
            continue

        if fields[0] == HOTSPOT_CONNECTION_NAME:
            return True

    return False


def _ethernet_devices() -> list[dict[str, str]]:
    result = _nmcli(
        [
            "--terse",
            "--fields",
            "DEVICE,TYPE,STATE,CONNECTION",
            "device",
            "status",
        ]
    )
    if not result.ok:
        return []

    devices: list[dict[str, str]] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        fields = _split_nmcli_line(line)
        while len(fields) < 4:
            fields.append("")
        device, device_type, state, connection = fields[:4]
        if device_type != "ethernet":
            continue
        devices.append(
            {
                "device": device,
                "type": device_type,
                "state": state,
                "connection": connection,
            }
        )
    return devices


def ethernet_interface() -> str | None:
    devices = _ethernet_devices()
    for device in devices:
        if device["state"] in {"connected", "connecting"}:
            return device["device"]
    if devices:
        return devices[0]["device"]
    for candidate in ("eth0", "end0", "enp1s0"):
        result = run(["ip", "-o", "link", "show", "dev", candidate])
        if result.ok:
            return candidate
    return None


def _ip_ipv4(interface: str) -> list[str]:
    result = run(
        [
            "ip",
            "-4",
            "-o",
            "addr",
            "show",
            "dev",
            interface,
        ]
    )
    if not result.ok:
        return []
    addresses: list[str] = []
    for line in result.stdout.splitlines():
        match = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+/\d+)", line)
        if match:
            addresses.append(match.group(1))
    return addresses


def _hostapd_hotspot_active() -> bool:
    result = run(["systemctl", "is-active", "hostapd.service"])
    if result.ok and result.stdout.strip() == "active":
        return True
    for interface in ("wlan0", "wlan1"):
        for address in _ip_ipv4(interface):
            if address.startswith("192.168.4.1/"):
                return True
    return False


def status() -> dict[str, Any]:
    """
    Return the current MineBox network status.

    Includes nested ethernet/wifi/hotspot objects for the setup wizard, plus
    flat fields for the dashboard network panel.
    """

    available = networkmanager_available()
    wifi_iface = wifi_interface()
    ethernet_iface = ethernet_interface()

    ethernet_connected = False
    ethernet_addresses: list[str] = []
    ethernet_ip = None
    ethernet_gateway = None
    ethernet_connection = None

    if ethernet_iface is not None:
        if available:
            devices = _ethernet_devices()
            selected = next(
                (device for device in devices if device["device"] == ethernet_iface),
                None,
            )
            if selected is not None:
                ethernet_connected = selected["state"] == "connected"
                ethernet_connection = (
                    selected["connection"]
                    if selected["connection"] not in {"", "--"}
                    else None
                )
            ethernet_addresses = _device_ipv4(ethernet_iface)
            ethernet_gateway = _device_gateway(ethernet_iface)
        if not ethernet_addresses:
            ethernet_addresses = _ip_ipv4(ethernet_iface)
        if ethernet_addresses:
            ethernet_ip = ethernet_addresses[0].split("/", 1)[0]
            if not ethernet_connected and not ethernet_ip.startswith("169.254."):
                ethernet_connected = True

    wifi_connected = False
    wifi_connection = None
    wifi_details: dict[str, Any] = {}
    wifi_addresses: list[str] = []
    wifi_ip = None
    wifi_gateway = None
    wifi_dns: list[str] = []

    # Prefer a client radio (USB wlan1) for join/status while hotspot owns wlan0.
    client_candidate = client_wifi_interface()
    status_wifi_iface = client_candidate or wifi_iface

    if available and status_wifi_iface is not None:
        devices = _wifi_devices()
        selected = next(
            (device for device in devices if device["device"] == status_wifi_iface),
            None,
        )
        if selected is not None:
            wifi_connected = selected["state"] == "connected"
            wifi_connection = (
                selected["connection"]
                if selected["connection"] not in {"", "--"}
                else None
            )
        active_wifi = _active_wifi_details(status_wifi_iface)
        if active_wifi is not None:
            wifi_details = active_wifi
            wifi_connected = True
        wifi_addresses = _device_ipv4(status_wifi_iface)
        if wifi_addresses:
            wifi_ip = wifi_addresses[0].split("/", 1)[0]
        wifi_gateway = _device_gateway(status_wifi_iface)
        wifi_dns = _device_dns(status_wifi_iface)

    hotspot_active = hotspot_is_active() or _hostapd_hotspot_active()
    hostapd_hotspot = _hostapd_hotspot_active()
    physical_wifi = _physical_wifi_interfaces()
    wifi_hardware_available = wifi_iface is not None or bool(physical_wifi)
    if wifi_iface is None and physical_wifi:
        wifi_iface = physical_wifi[0]
    if status_wifi_iface is not None:
        wifi_iface = status_wifi_iface

    # Prefer the LAN uplink for "connected" reporting. Setup hotspot can run
    # at the same time on wlan0 without replacing ethernet.
    if ethernet_connected:
        connection_type = "ethernet"
    elif wifi_connected:
        connection_type = "wifi"
    elif hotspot_active:
        connection_type = "hotspot"
    else:
        connection_type = None

    primary_ip = ethernet_ip or wifi_ip
    primary_gateway = ethernet_gateway or wifi_gateway
    primary_addresses = ethernet_addresses or wifi_addresses
    primary_dns = wifi_dns
    if ethernet_iface and ethernet_connected:
        primary_dns = _device_dns(ethernet_iface) or primary_dns

    if connection_type == "ethernet":
        display_name = ethernet_connection or "Ethernet"
        primary_interface = ethernet_iface
        signal = None
        security = "Ethernet"
    elif connection_type == "wifi":
        display_name = wifi_details.get("ssid") or wifi_connection or "Wi-Fi"
        primary_interface = wifi_iface
        signal = wifi_details.get("signal")
        security = wifi_details.get("security")
    elif connection_type == "hotspot":
        display_name = DEFAULT_HOTSPOT_SSID
        primary_interface = wifi_iface
        signal = None
        security = "WPA2 hotspot"
        if not primary_ip:
            primary_ip = DEFAULT_HOTSPOT_ADDRESS.split("/", 1)[0]
    else:
        display_name = None
        primary_interface = ethernet_iface or wifi_iface
        signal = None
        security = None

    wifi_scan_blocked_reason = None
    client_iface = client_wifi_interface()
    if not wifi_hardware_available:
        wifi_scan_blocked_reason = "No Wi-Fi adapter was detected."
    elif client_iface is None and hotspot_radio_in_use():
        wifi_scan_blocked_reason = (
            "The setup hotspot is using the onboard Wi-Fi radio. "
            "Plug in a USB Wi-Fi adapter, or stop the hotspot to scan."
        )
    elif client_iface is None:
        wifi_scan_blocked_reason = "No Wi-Fi adapter was detected."
    elif available and not _wifi_devices():
        wifi_scan_blocked_reason = (
            "A Wi-Fi adapter is present, but NetworkManager is not managing it."
        )

    response: dict[str, Any] = {
        "networkmanager_available": available,
        "wifi_available": wifi_hardware_available,
        "ethernet_available": ethernet_iface is not None,
        "interface": primary_interface,
        "wifi_interface": wifi_iface,
        "client_wifi_interface": client_iface,
        "hotspot_interface": HOTSPOT_INTERFACE if hotspot_active else None,
        "ethernet_interface": ethernet_iface,
        "hostname": _hostname(),
        "local_hostname": f"{_hostname()}.local",
        "connected": bool(ethernet_connected or wifi_connected),
        "connection_type": connection_type,
        "connection_name": ethernet_connection or wifi_connection,
        "display_name": display_name,
        "ssid": (
            wifi_details.get("ssid")
            if connection_type == "wifi"
            else (DEFAULT_HOTSPOT_SSID if connection_type == "hotspot" else None)
        ),
        "signal": signal,
        "security": security,
        "frequency": wifi_details.get("frequency") if connection_type == "wifi" else None,
        "rate": wifi_details.get("rate") if connection_type == "wifi" else None,
        "ipv4_addresses": primary_addresses,
        "ip_address": primary_ip,
        "gateway": primary_gateway,
        "dns": primary_dns,
        "hotspot_active": hotspot_active,
        "hotspot_mode": "hostapd" if hostapd_hotspot else ("networkmanager" if hotspot_is_active() else None),
        "hotspot_connection_name": HOTSPOT_CONNECTION_NAME,
        "wifi_scan_blocked_reason": wifi_scan_blocked_reason,
        "ethernet": {
            "available": ethernet_iface is not None,
            "connected": ethernet_connected,
            "interface": ethernet_iface,
            "connection_name": ethernet_connection,
            "ipv4_addresses": ethernet_addresses,
            "ip_address": ethernet_ip,
            "gateway": ethernet_gateway,
        },
        "wifi": {
            "available": wifi_hardware_available,
            "connected": wifi_connected,
            "interface": client_iface or wifi_iface,
            "connection_name": wifi_connection,
            "ssid": wifi_details.get("ssid"),
            "signal": wifi_details.get("signal"),
            "security": wifi_details.get("security"),
            "ipv4_addresses": wifi_addresses,
            "ip_address": wifi_ip,
            "gateway": wifi_gateway,
            "managed_by_networkmanager": bool(_wifi_devices()),
        },
        "hotspot": {
            "active": hotspot_active,
            "mode": "hostapd" if hostapd_hotspot else ("networkmanager" if hotspot_is_active() else None),
            "connection_name": HOTSPOT_CONNECTION_NAME,
            "ssid": DEFAULT_HOTSPOT_SSID,
            "address": DEFAULT_HOTSPOT_ADDRESS.split("/", 1)[0],
        },
    }

    return response


def scan_wifi(rescan: bool = True) -> dict[str, Any]:
    """
    Scan for nearby Wi-Fi networks.

    Duplicate SSIDs are combined, keeping the strongest signal.
    Uses a client Wi-Fi adapter when the setup hotspot owns wlan0.
    """

    interface = client_wifi_interface()

    if interface is None:
        if hotspot_radio_in_use():
            return {
                "ok": False,
                "message": (
                    "The setup hotspot is using the onboard Wi-Fi radio. "
                    "Plug in a USB Wi-Fi adapter, or stop the hotspot to scan."
                ),
                "interface": None,
                "networks": [],
            }
        return {
            "ok": False,
            "message": "No Wi-Fi adapter was detected.",
            "interface": None,
            "networks": [],
        }

    # Only block when the only radio is the hotspot AP itself.
    if interface == HOTSPOT_INTERFACE and hotspot_radio_in_use():
        return {
            "ok": False,
            "message": (
                "The setup hotspot is using the onboard Wi-Fi radio. "
                "Plug in a USB Wi-Fi adapter, or stop the hotspot to scan."
            ),
            "interface": interface,
            "networks": [],
        }

    if not any(device["device"] == interface for device in _wifi_devices()):
        return {
            "ok": False,
            "message": (
                "Wi-Fi hardware was found, but NetworkManager is not managing "
                f"{interface}, so scanning is unavailable right now."
            ),
            "interface": interface,
            "networks": [],
        }

    if rescan:
        _nmcli(
            [
                "device",
                "wifi",
                "rescan",
                "ifname",
                interface,
            ],
            timeout=20,
        )

    result = _nmcli(
        [
            "--terse",
            "--fields",
            "IN-USE,SSID,SIGNAL,SECURITY,FREQ,CHAN,RATE",
            "device",
            "wifi",
            "list",
            "ifname",
            interface,
        ],
        timeout=30,
    )

    if not result.ok:
        return {
            "ok": False,
            "message": result.message,
            "interface": interface,
            "networks": [],
        }

    networks_by_ssid: dict[str, dict[str, Any]] = {}

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        fields = _split_nmcli_line(line)

        while len(fields) < 7:
            fields.append("")

        (
            in_use,
            ssid,
            signal,
            security,
            frequency,
            channel,
            rate,
        ) = fields[:7]

        ssid = ssid.strip()

        # Hidden networks do not have a selectable SSID.
        if not ssid:
            continue

        try:
            signal_value = max(0, min(100, int(signal)))
        except ValueError:
            signal_value = 0

        network = {
            "ssid": ssid,
            "signal": signal_value,
            "security": security or "Open",
            "secured": bool(
                security
                and security not in {
                    "--",
                    "NONE",
                    "Open",
                }
            ),
            "frequency": frequency,
            "channel": channel,
            "rate": rate,
            "connected": in_use in {"*", "yes"},
        }

        existing = networks_by_ssid.get(ssid)

        if (
            existing is None
            or network["connected"]
            or signal_value > existing["signal"]
        ):
            networks_by_ssid[ssid] = network

    networks = sorted(
        networks_by_ssid.values(),
        key=lambda item: (
            not item["connected"],
            -item["signal"],
            item["ssid"].lower(),
        ),
    )

    if not networks:
        return {
            "ok": True,
            "message": "No nearby Wi-Fi networks were found.",
            "interface": interface,
            "networks": [],
        }

    return {
        "ok": True,
        "message": f"Found {len(networks)} Wi-Fi networks.",
        "interface": interface,
        "networks": networks,
    }


def _valid_ssid(ssid: str) -> bool:
    encoded = ssid.encode(
        "utf-8",
        errors="ignore",
    )

    return 1 <= len(encoded) <= 32


def _valid_wifi_password(password: str) -> bool:
    """
    WPA/WPA2 passphrases are normally 8-63 characters.

    A 64-character hexadecimal value is also valid.
    """

    if 8 <= len(password) <= 63:
        return True

    return bool(
        re.fullmatch(
            r"[0-9a-fA-F]{64}",
            password,
        )
    )


def connect_wifi(
    ssid: str,
    password: str | None = None,
    hidden: bool = False,
) -> CommandResult:
    """
    Connect MineBox to a Wi-Fi network.

    For secured networks, password must be provided.
    Open networks may use an empty password.
    """

    interface = client_wifi_interface()

    if interface is None:
        return CommandResult(
            False,
            stderr="No Wi-Fi adapter was detected.",
            returncode=1,
        )

    ssid = str(ssid).strip()

    if not _valid_ssid(ssid):
        return CommandResult(
            False,
            stderr=(
                "The Wi-Fi name must contain between "
                "1 and 32 bytes."
            ),
            returncode=1,
        )

    password = (
        str(password)
        if password is not None
        else ""
    )

    # Only tear down the setup hotspot when we must reuse its radio.
    if interface == HOTSPOT_INTERFACE and hotspot_radio_in_use():
        stop_hotspot()
    elif hotspot_is_active() and interface == HOTSPOT_INTERFACE:
        stop_hotspot()

    command = [
        "device",
        "wifi",
        "connect",
        ssid,
        "ifname",
        interface,
    ]

    if password:
        command.extend(
            [
                "password",
                password,
            ]
        )

    if hidden:
        command.extend(
            [
                "hidden",
                "yes",
            ]
        )

    result = _nmcli(
        command,
        timeout=60,
    )

    if not result.ok:
        return CommandResult(
            False,
            stdout=result.stdout,
            stderr=result.stderr or (
                f"Could not connect to {ssid}."
            ),
            returncode=result.returncode,
        )

    return CommandResult(
        True,
        stdout=f"MineBox connected to {ssid}.",
    )


def disconnect_wifi() -> CommandResult:
    interface = wifi_interface()

    if interface is None:
        return CommandResult(
            False,
            stderr="No Wi-Fi adapter was detected.",
            returncode=1,
        )

    result = _nmcli(
        [
            "device",
            "disconnect",
            interface,
        ],
        timeout=30,
    )

    if not result.ok:
        return result

    return CommandResult(
        True,
        stdout="Wi-Fi disconnected.",
    )


def saved_wifi_connections() -> list[dict[str, Any]]:
    """
    Return saved NetworkManager Wi-Fi connections.
    Passwords are never included.
    """

    result = _nmcli(
        [
            "--terse",
            "--fields",
            "NAME,UUID,TYPE,AUTOCONNECT,DEVICE",
            "connection",
            "show",
        ]
    )

    if not result.ok:
        return []

    connections: list[dict[str, Any]] = []

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        fields = _split_nmcli_line(line)

        while len(fields) < 5:
            fields.append("")

        name, uuid, connection_type, autoconnect, device = fields[:5]

        if connection_type not in {
            "802-11-wireless",
            "wifi",
        }:
            continue

        if name == HOTSPOT_CONNECTION_NAME:
            continue

        connections.append(
            {
                "name": name,
                "uuid": uuid,
                "autoconnect": autoconnect.lower()
                in {
                    "yes",
                    "true",
                    "1",
                },
                "active": bool(device and device != "--"),
                "device": (
                    device
                    if device and device != "--"
                    else None
                ),
            }
        )

    return connections


def forget_wifi(connection_name: str) -> CommandResult:
    connection_name = str(connection_name).strip()

    if not connection_name:
        return CommandResult(
            False,
            stderr="A saved connection name is required.",
            returncode=1,
        )

    if connection_name == HOTSPOT_CONNECTION_NAME:
        return CommandResult(
            False,
            stderr=(
                "The MineBox hotspot cannot be removed "
                "with the forget-network function."
            ),
            returncode=1,
        )

    result = _nmcli(
        [
            "connection",
            "delete",
            connection_name,
        ],
        timeout=30,
    )

    if not result.ok:
        return result

    return CommandResult(
        True,
        stdout=f"Forgot saved network {connection_name}.",
    )


def start_hotspot(
    ssid: str = DEFAULT_HOTSPOT_SSID,
    password: str = "",
) -> CommandResult:
    """
    Start the MineBox setup hotspot.

    NetworkManager's shared IPv4 mode supplies DHCP and NAT.
    """

    if _hostapd_hotspot_active():
        return CommandResult(
            True,
            stdout=(
                "The MineBox setup hotspot is already active "
                f"as {DEFAULT_HOTSPOT_SSID} (192.168.4.1)."
            ),
        )

    if hotspot_is_active():
        return CommandResult(
            True,
            stdout="The MineBox hotspot is already active.",
        )

    interface = wifi_interface()

    if interface is None:
        return CommandResult(
            False,
            stderr="No Wi-Fi adapter was detected.",
            returncode=1,
        )

    ssid = str(ssid).strip()
    password = str(password)

    if not _valid_ssid(ssid):
        return CommandResult(
            False,
            stderr=(
                "The hotspot name must contain between "
                "1 and 32 bytes."
            ),
            returncode=1,
        )

    if not _valid_wifi_password(password):
        return CommandResult(
            False,
            stderr=(
                "The hotspot password must contain "
                "8 to 63 characters."
            ),
            returncode=1,
        )

    # Remove the old hotspot profile so changed credentials apply cleanly.
    _nmcli(
        [
            "connection",
            "delete",
            HOTSPOT_CONNECTION_NAME,
        ],
        timeout=20,
    )

    create_result = _nmcli(
        [
            "connection",
            "add",
            "type",
            "wifi",
            "ifname",
            interface,
            "con-name",
            HOTSPOT_CONNECTION_NAME,
            "ssid",
            ssid,
            "802-11-wireless.mode",
            "ap",
            "802-11-wireless.band",
            "bg",
            "ipv4.method",
            "shared",
            "ipv4.addresses",
            DEFAULT_HOTSPOT_ADDRESS,
            "ipv6.method",
            "disabled",
            "wifi-sec.key-mgmt",
            "wpa-psk",
            "wifi-sec.psk",
            password,
        ],
        timeout=30,
    )

    if not create_result.ok:
        return CommandResult(
            False,
            stdout=create_result.stdout,
            stderr=create_result.stderr or (
                "Could not create the MineBox hotspot profile."
            ),
            returncode=create_result.returncode,
        )

    modify_result = _nmcli(
        [
            "connection",
            "modify",
            HOTSPOT_CONNECTION_NAME,
            "connection.autoconnect",
            "no",
        ],
        timeout=20,
    )

    if not modify_result.ok:
        return modify_result

    activate_result = _nmcli(
        [
            "connection",
            "up",
            HOTSPOT_CONNECTION_NAME,
            "ifname",
            interface,
        ],
        timeout=60,
    )

    if not activate_result.ok:
        return CommandResult(
            False,
            stdout=activate_result.stdout,
            stderr=activate_result.stderr or (
                "The hotspot profile was created, "
                "but it could not be activated."
            ),
            returncode=activate_result.returncode,
        )

    return CommandResult(
        True,
        stdout=(
            f"MineBox hotspot {ssid} started. "
            "Open http://192.168.4.1 (or https://192.168.4.1:8080 if HTTPS is on)."
        ),
    )


def stop_hotspot() -> CommandResult:
    messages: list[str] = []

    if hotspot_is_active():
        result = _nmcli(
            [
                "connection",
                "down",
                HOTSPOT_CONNECTION_NAME,
            ],
            timeout=30,
        )
        if not result.ok:
            return result
        messages.append("NetworkManager hotspot stopped.")

    if _hostapd_hotspot_active():
        stop_hostapd = run(
            [
                "sudo",
                "-n",
                "/usr/bin/systemctl",
                "stop",
                "hostapd.service",
            ],
            timeout=30,
        )
        # dnsmasq may also be tied to the setup hotspot.
        run(
            [
                "sudo",
                "-n",
                "/usr/bin/systemctl",
                "stop",
                "dnsmasq.service",
            ],
            timeout=30,
        )
        if not stop_hostapd.ok:
            return CommandResult(
                False,
                stderr=(
                    stop_hostapd.stderr
                    or "Could not stop the MineBox setup hotspot service."
                ),
                returncode=stop_hostapd.returncode,
            )
        messages.append("Setup hotspot stopped.")

    if not messages:
        return CommandResult(
            True,
            stdout="The MineBox hotspot is already stopped.",
        )

    return CommandResult(
        True,
        stdout=" ".join(messages),
    )
