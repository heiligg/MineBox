from __future__ import annotations

import re
import socket
import struct
from pathlib import Path

from config import RCON_HOST, RCON_PASSWORD, RCON_PORT
from services import servers
from services.system import CommandResult


SERVERDATA_AUTH = 3
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0


def _packet(request_id: int, packet_type: int, body: str) -> bytes:
    payload = (
        struct.pack("<ii", request_id, packet_type)
        + body.encode("utf-8")
        + b"\x00\x00"
    )
    return struct.pack("<i", len(payload)) + payload


def _recv_exact(sock: socket.socket, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise ConnectionError("RCON connection closed unexpectedly")
        data.extend(chunk)
    return bytes(data)


def _recv_packet(sock: socket.socket) -> tuple[int, int, str]:
    size = struct.unpack("<i", _recv_exact(sock, 4))[0]
    if size < 10 or size > 10_000_000:
        raise ValueError("Invalid RCON packet size")
    payload = _recv_exact(sock, size)
    request_id, packet_type = struct.unpack("<ii", payload[:8])
    body = payload[8:-2].decode("utf-8", errors="replace")
    return request_id, packet_type, body


def _read_properties(path: Path) -> dict[str, str]:
    props: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return props
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        props[key.strip()] = value.strip()
    return props


def resolve_credentials() -> tuple[str, int, str]:
    """Return (host, port, password) for the active Minecraft server."""
    host = RCON_HOST
    port = int(RCON_PORT)
    password = RCON_PASSWORD

    active = servers.active_server()
    if active is None:
        return host, port, password

    port = int(active.rcon_port or port)
    server_dir = Path(active.directory)
    props = _read_properties(server_dir / "server.properties")

    if props.get("rcon.port", "").strip().isdigit():
        port = int(props["rcon.port"].strip())

    prop_password = props.get("rcon.password", "").strip()
    if prop_password:
        password = prop_password
    else:
        password_file = server_dir / ".minebox-rcon-password"
        try:
            stored = password_file.read_text(encoding="utf-8").strip()
        except OSError:
            stored = ""
        if stored:
            password = stored

    return host, port, password


def ensure_properties(server_dir: Path | None = None) -> dict[str, str]:
    """Make sure enable-rcon and credentials exist (Forge often wipes them)."""
    if server_dir is None:
        active = servers.active_server()
        if active is None:
            return {}
        server_dir = Path(active.directory)

    properties_path = server_dir / "server.properties"
    password_file = server_dir / ".minebox-rcon-password"

    try:
        password = password_file.read_text(encoding="utf-8").strip()
    except OSError:
        password = ""
    if not password:
        password = RCON_PASSWORD
        try:
            password_file.write_text(password + "\n", encoding="utf-8")
        except OSError:
            pass

    active = servers.active_server()
    rcon_port = str(active.rcon_port if active is not None else RCON_PORT)

    updates = {
        "enable-rcon": "true",
        "rcon.port": rcon_port,
        "rcon.password": password,
        "broadcast-rcon-to-ops": "true",
    }

    existing_lines: list[str] = []
    if properties_path.is_file():
        try:
            existing_lines = properties_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            existing_lines = []

    seen: set[str] = set()
    output: list[str] = []
    for raw in existing_lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(raw.rstrip("\n"))
            continue
        key, _value = stripped.split("=", 1)
        key = key.strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(raw.rstrip("\n"))

    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")

    properties_path.parent.mkdir(parents=True, exist_ok=True)
    properties_path.write_text("\n".join(output) + "\n", encoding="utf-8")
    return updates


def send(command: str, timeout: float = 4.0) -> CommandResult:
    command = command.strip()
    if not command:
        return CommandResult(False, stderr="RCON command was empty.")

    host, port, password = resolve_credentials()

    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as sock:
            sock.settimeout(timeout)
            auth_id = 100
            sock.sendall(_packet(auth_id, SERVERDATA_AUTH, password))
            response_id, _response_type, _response_body = _recv_packet(sock)
            if response_id == -1:
                return CommandResult(
                    False,
                    stderr=(
                        "RCON authentication failed. MineBox will repair "
                        "enable-rcon / rcon.password on the next server restart."
                    ),
                )

            command_id = 101
            sock.sendall(_packet(command_id, SERVERDATA_EXECCOMMAND, command))
            response_id, response_type, body = _recv_packet(sock)
            if response_id != command_id:
                return CommandResult(
                    False, stderr="RCON returned an unexpected response."
                )
            if response_type not in (
                SERVERDATA_RESPONSE_VALUE,
                SERVERDATA_EXECCOMMAND,
            ):
                return CommandResult(
                    False, stderr="RCON returned an invalid packet type."
                )
            return CommandResult(True, stdout=body.strip())
    except (OSError, ValueError, ConnectionError, struct.error) as exc:
        return CommandResult(False, stderr=f"RCON unavailable: {exc}")


def command(command_text: str, timeout: float = 4.0) -> str:
    """Execute an RCON command and return the response body (or raise)."""
    result = send(command_text, timeout=timeout)
    if not result.ok:
        raise RuntimeError(result.stderr or "RCON command failed.")
    return result.stdout or ""


def players() -> tuple[list[str], int] | None:
    """
    Return (player_names, max_players) from the Minecraft list command.

    Returns None when RCON is unavailable or the response cannot be parsed.
    """

    result = send("list")
    if not result.ok:
        return None

    text = (result.stdout or "").strip()
    if not text:
        return None

    match = re.search(
        r"There are (\d+) of a max(?:imum)? of (\d+) players online(?:[:\s]*(.*))?$",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        match = re.search(
            r"There are (\d+)/(\d+) players online(?:[:\s]*(.*))?$",
            text,
            re.IGNORECASE | re.DOTALL,
        )
    if match is None:
        return None

    try:
        online_count = int(match.group(1))
        max_players = int(match.group(2))
    except (TypeError, ValueError):
        return None

    names_blob = (match.group(3) or "").strip()
    names: list[str] = []
    if names_blob:
        names = [
            name.strip()
            for name in re.split(r",\s*", names_blob)
            if name.strip()
        ]

    if not names and online_count == 0:
        return [], max_players

    if names:
        return names, max_players

    return [f"player-{index}" for index in range(online_count)], max_players
