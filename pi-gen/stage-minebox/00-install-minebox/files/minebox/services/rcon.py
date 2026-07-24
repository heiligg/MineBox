from __future__ import annotations

import socket
import struct
from config import RCON_HOST, RCON_PORT, RCON_PASSWORD
from services.system import CommandResult

SERVERDATA_AUTH = 3
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0


def _packet(request_id: int, packet_type: int, body: str) -> bytes:
    payload = struct.pack("<ii", request_id, packet_type) + body.encode("utf-8") + b"\x00\x00"
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


def send(command: str, timeout: float = 4.0) -> CommandResult:
    command = command.strip()
    if not command:
        return CommandResult(False, stderr="RCON command was empty.")

    try:
        with socket.create_connection((RCON_HOST, int(RCON_PORT)), timeout=timeout) as sock:
            sock.settimeout(timeout)
            auth_id = 100
            sock.sendall(_packet(auth_id, SERVERDATA_AUTH, RCON_PASSWORD))
            response_id, _response_type, _response_body = _recv_packet(sock)
            if response_id == -1:
                return CommandResult(False, stderr="RCON authentication failed.")

            command_id = 101
            sock.sendall(_packet(command_id, SERVERDATA_EXECCOMMAND, command))
            response_id, response_type, body = _recv_packet(sock)
            if response_id != command_id:
                return CommandResult(False, stderr="RCON returned an unexpected response.")
            if response_type not in (SERVERDATA_RESPONSE_VALUE, SERVERDATA_EXECCOMMAND):
                return CommandResult(False, stderr="RCON returned an invalid packet type.")
            return CommandResult(True, stdout=body.strip())
    except (OSError, ValueError, ConnectionError, struct.error) as exc:
        return CommandResult(False, stderr=f"RCON unavailable: {exc}")


def players() -> tuple[list[str], int] | None:
    """Return the online player names and maximum player count via RCON."""
    result = send("list")
    if not result.ok:
        return None

    body = result.stdout.strip()
    # Vanilla responses look like:
    # "There are 0 of a max of 20 players online:"
    # or "There are 2 of a max of 20 players online: Alex, Steve"
    import re
    match = re.search(
        r"There are\s+(\d+)\s+of a max of\s+(\d+)\s+players online:?\s*(.*)",
        body,
        re.IGNORECASE,
    )
    if not match:
        return None

    maximum = int(match.group(2))
    names_text = match.group(3).strip()
    names = [name.strip() for name in names_text.split(",") if name.strip()]
    return names, maximum
