from __future__ import annotations

import re
import socket
from typing import Any

from services.system import CommandResult, run


HOTSPOT_CONNECTION_NAME = "MineBox-Hotspot"
DEFAULT_HOTSPOT_SSID = "MineBox-Setup"
DEFAULT_HOTSPOT_ADDRESS = "192.168.4.1/24"


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
    available Wi-Fi device.
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

    return None


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


def status() -> dict[str, Any]:
    """
    Return the current MineBox network status.
    """

    available = networkmanager_available()
    interface = wifi_interface()

    response: dict[str, Any] = {
        "networkmanager_available": available,
        "wifi_available": interface is not None,
        "interface": interface,
        "hostname": _hostname(),
        "local_hostname": f"{_hostname()}.local",
        "connected": False,
        "connection_type": None,
        "connection_name": None,
        "ssid": None,
        "signal": None,
        "security": None,
        "frequency": None,
        "rate": None,
        "ipv4_addresses": [],
        "ip_address": None,
        "gateway": None,
        "dns": [],
        "hotspot_active": False,
        "hotspot_connection_name": HOTSPOT_CONNECTION_NAME,
    }

    if not available or interface is None:
        return response

    devices = _wifi_devices()
    selected_device = next(
        (
            device
            for device in devices
            if device["device"] == interface
        ),
        None,
    )

    if selected_device is not None:
        response["connected"] = (
            selected_device["state"] == "connected"
        )
        response["connection_name"] = (
            selected_device["connection"]
            if selected_device["connection"] not in {
                "",
                "--",
            }
            else None
        )

    response["hotspot_active"] = hotspot_is_active()

    if response["hotspot_active"]:
        response["connection_type"] = "hotspot"
    elif response["connected"]:
        response["connection_type"] = "wifi"

    active_wifi = _active_wifi_details(interface)

    if active_wifi is not None:
        response.update(active_wifi)

    addresses = _device_ipv4(interface)
    response["ipv4_addresses"] = addresses

    if addresses:
        response["ip_address"] = addresses[0].split("/", 1)[0]

    response["gateway"] = _device_gateway(interface)
    response["dns"] = _device_dns(interface)

    return response


def scan_wifi(rescan: bool = True) -> dict[str, Any]:
    """
    Scan for nearby Wi-Fi networks.

    Duplicate SSIDs are combined, keeping the strongest signal.
    """

    interface = wifi_interface()

    if interface is None:
        return {
            "ok": False,
            "message": "No Wi-Fi adapter was detected.",
            "interface": None,
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

    interface = wifi_interface()

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

    # Turn off the setup hotspot before trying to join another network.
    if hotspot_is_active():
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
            "Open http://192.168.4.1 after connecting."
        ),
    )


def stop_hotspot() -> CommandResult:
    if not hotspot_is_active():
        return CommandResult(
            True,
            stdout="The MineBox hotspot is already stopped.",
        )

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

    return CommandResult(
        True,
        stdout="MineBox hotspot stopped.",
    )
