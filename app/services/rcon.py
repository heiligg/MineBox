from __future__ import annotations

import socket
import struct
from pathlib import Path


RCON_HOST = "127.0.0.1"
RCON_PORT = 25575
RCON_PASSWORD_FILE = Path("/opt/minecraft/.minebox-rcon-password")

SERVERDATA_AUTH = 3
SERVERDATA_EXECCOMMAND = 2


class RconError(RuntimeError):
    pass


def _read_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()

    while len(data) < size:
        chunk = sock.recv(size - len(data))

        if not chunk:
            raise RconError("RCON connection closed unexpectedly.")

        data.extend(chunk)

    return bytes(data)


def _send_packet(
    sock: socket.socket,
    request_id: int,
    packet_type: int,
    body: str,
) -> None:
    payload = struct.pack(
        "<ii",
        request_id,
        packet_type,
    ) + body.encode("utf-8") + b"\x00\x00"

    sock.sendall(struct.pack("<i", len(payload)) + payload)


def _read_packet(sock: socket.socket) -> tuple[int, int, str]:
    packet_length = struct.unpack("<i", _read_exact(sock, 4))[0]

    if packet_length < 10 or packet_length > 1024 * 1024:
        raise RconError("Invalid RCON packet length.")

    payload = _read_exact(sock, packet_length)

    request_id, packet_type = struct.unpack("<ii", payload[:8])
    body = payload[8:-2].decode("utf-8", errors="replace")

    return request_id, packet_type, body


def _password() -> str:
    try:
        password = RCON_PASSWORD_FILE.read_text(
            encoding="utf-8"
        ).strip()
    except OSError as error:
        raise RconError(
            "MineBox RCON password file could not be read."
        ) from error

    if not password:
        raise RconError("MineBox RCON password is empty.")

    return password


def command(command_text: str) -> str:
    password = _password()

    try:
        with socket.create_connection(
            (RCON_HOST, RCON_PORT),
            timeout=5,
        ) as sock:
            sock.settimeout(5)

            _send_packet(
                sock,
                request_id=1,
                packet_type=SERVERDATA_AUTH,
                body=password,
            )

            auth_id, _, _ = _read_packet(sock)

            if auth_id == -1:
                raise RconError("RCON authentication failed.")

            _send_packet(
                sock,
                request_id=2,
                packet_type=SERVERDATA_EXECCOMMAND,
                body=command_text,
            )

            response_id, _, response_body = _read_packet(sock)

            if response_id == -1:
                raise RconError("RCON command failed.")

            return response_body.strip()

    except OSError as error:
        raise RconError(
            f"Could not connect to Minecraft RCON: {error}"
        ) from error


def players() -> tuple[list[str], int]:
    response = command("list")

    # Typical response:
    # There are 0/20 players online:
    # There are 2/20 players online: Alex, Steve

    if "/" not in response:
        raise RconError(f"Unexpected player-list response: {response}")

    prefix, _, names_text = response.partition(":")
    words = prefix.replace("/", " ").split()

    current = None
    maximum = None

    for index, word in enumerate(words):
        if word.isdigit() and index + 1 < len(words):
            next_word = words[index + 1]

            if next_word.isdigit():
                current = int(word)
                maximum = int(next_word)
                break

    if current is None or maximum is None:
        raise RconError(f"Could not parse player counts: {response}")

    names = [
        name.strip()
        for name in names_text.split(",")
        if name.strip()
    ]

    return names, maximum
