from __future__ import annotations

import os
import secrets
from pathlib import Path


SERVER_DIR = Path("/opt/minecraft")
RCON_PASSWORD_FILE = SERVER_DIR / ".minebox-rcon-password"


def install_directory() -> Path:
    SERVER_DIR.mkdir(parents=True, exist_ok=True)
    (SERVER_DIR / "logs").mkdir(exist_ok=True)
    (SERVER_DIR / "world").mkdir(exist_ok=True)
    return SERVER_DIR


def _get_or_create_rcon_password() -> str:
    if RCON_PASSWORD_FILE.exists():
        password = RCON_PASSWORD_FILE.read_text(
            encoding="utf-8"
        ).strip()

        if password:
            return password

    password = secrets.token_urlsafe(24)

    RCON_PASSWORD_FILE.write_text(
        password + "\n",
        encoding="utf-8",
    )

    os.chmod(RCON_PASSWORD_FILE, 0o600)

    return password


def write_eula() -> None:
    (SERVER_DIR / "eula.txt").write_text(
        "eula=true\n",
        encoding="utf-8",
    )


def write_properties(server_name: str) -> None:
    rcon_password = _get_or_create_rcon_password()

    properties = f"""motd={server_name}
server-port=25565
enable-query=false
enable-rcon=true
rcon.port=25575
rcon.password={rcon_password}
broadcast-rcon-to-ops=true
online-mode=true
difficulty=easy
gamemode=survival
max-players=20
view-distance=10
simulation-distance=10
"""

    (SERVER_DIR / "server.properties").write_text(
        properties,
        encoding="utf-8",
    )


def write_start_script(memory_gb: int) -> None:
    script = f"""#!/bin/bash

cd /opt/minecraft

exec java -Xms{memory_gb}G -Xmx{memory_gb}G -jar server.jar nogui
"""

    path = SERVER_DIR / "start.sh"
    path.write_text(script, encoding="utf-8")
    os.chmod(path, 0o755)


def initialize(server_name: str, memory_gb: int) -> dict:
    install_directory()
    write_eula()
    write_properties(server_name)
    write_start_script(memory_gb)

    return {
        "success": True,
        "directory": str(SERVER_DIR),
        "server_name": server_name,
        "memory_gb": memory_gb,
    }
