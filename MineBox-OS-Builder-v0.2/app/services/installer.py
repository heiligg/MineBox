from __future__ import annotations

import os
import secrets
from pathlib import Path

from services.servers import ServerInstance


def install_directory(instance: ServerInstance) -> Path:
    server_dir = Path(instance.directory)
    server_dir.mkdir(parents=True, exist_ok=False)
    (server_dir / "logs").mkdir()
    (server_dir / "world").mkdir()
    return server_dir


def _get_or_create_rcon_password(server_dir: Path) -> str:
    password_file = server_dir / ".minebox-rcon-password"

    if password_file.exists():
        password = password_file.read_text(encoding="utf-8").strip()
        if password:
            return password

    password = secrets.token_urlsafe(24)
    password_file.write_text(password + "\n", encoding="utf-8")
    os.chmod(password_file, 0o600)
    return password


def write_eula(server_dir: Path) -> None:
    (server_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")


def write_properties(instance: ServerInstance, server_dir: Path) -> None:
    rcon_password = _get_or_create_rcon_password(server_dir)

    properties = f"""motd={instance.name}
server-port={instance.port}
enable-query=false
enable-rcon=true
rcon.port={instance.rcon_port}
rcon.password={rcon_password}
broadcast-rcon-to-ops=true
online-mode=true
difficulty=easy
gamemode=survival
max-players=20
view-distance=10
simulation-distance=10
"""

    (server_dir / "server.properties").write_text(properties, encoding="utf-8")


def write_start_script(instance: ServerInstance, server_dir: Path) -> None:
    main_jar = instance.main_jar or "server.jar"
    run_sh = server_dir / "run.sh"
    if (instance.loader or "").lower() in {"forge", "neoforge"} and run_sh.is_file():
        launch = 'exec /bin/bash ./run.sh nogui'
    elif main_jar.startswith("@"):
        launch = (
            f'exec java -Xms{instance.memory_gb}G -Xmx{instance.memory_gb}G '
            f'@user_jvm_args.txt {main_jar} nogui'
        )
    else:
        launch = (
            f'exec java -Xms{instance.memory_gb}G -Xmx{instance.memory_gb}G '
            f'-jar {main_jar} nogui'
        )
    script = f"""#!/bin/bash
set -e
cd {server_dir}
{launch}
"""

    path = server_dir / "start.sh"
    path.write_text(script, encoding="utf-8")
    os.chmod(path, 0o755)


def initialize(instance: ServerInstance) -> dict:
    server_dir = install_directory(instance)
    write_eula(server_dir)
    write_properties(instance, server_dir)
    write_start_script(instance, server_dir)

    return {
        "success": True,
        "directory": str(server_dir),
        "server_id": instance.server_id,
        "server_name": instance.name,
        "memory_gb": instance.memory_gb,
        "port": instance.port,
        "rcon_port": instance.rcon_port,
        "loader": instance.loader,
    }
