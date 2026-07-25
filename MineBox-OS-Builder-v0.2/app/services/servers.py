from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def _minecraft_root() -> Path:
    configured = os.environ.get("MINEBOX_MINECRAFT_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path("/opt/minecraft")


MINECRAFT_ROOT = _minecraft_root()
SERVERS_DIR = MINECRAFT_ROOT / "servers"
METADATA_DIR = MINECRAFT_ROOT / "metadata"
REGISTRY_FILE = METADATA_DIR / "servers.json"
ACTIVE_SERVER_FILE = METADATA_DIR / "active_server"
DEFAULT_SERVER_PORT = 25565
DEFAULT_RCON_PORT = 25575


class ServerManagerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServerInstance:
    server_id: str
    name: str
    directory: str
    version: str
    memory_gb: int
    port: int
    rcon_port: int


def slugify_server_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ServerManagerError("The server name must contain at least one letter or number.")
    return slug[:48]


def ensure_layout() -> None:
    SERVERS_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)


def server_directory(server_id: str) -> Path:
    clean_id = slugify_server_id(server_id)
    return SERVERS_DIR / clean_id


def _load_registry() -> dict[str, Any]:
    ensure_layout()
    if not REGISTRY_FILE.exists():
        return {"version": 1, "servers": {}}

    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ServerManagerError(f"Could not read the server registry: {error}") from error

    if not isinstance(data, dict) or not isinstance(data.get("servers"), dict):
        raise ServerManagerError("The server registry is invalid.")

    return data


def _save_registry(data: dict[str, Any]) -> None:
    ensure_layout()
    temporary = REGISTRY_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(REGISTRY_FILE)


def list_servers() -> list[ServerInstance]:
    registry = _load_registry()
    server_instances: list[ServerInstance] = []
    for server_id, raw in registry["servers"].items():
        server_instances.append(
            ServerInstance(
                server_id=server_id,
                name=str(raw.get("name", server_id)),
                directory=str(raw.get("directory", server_directory(server_id))),
                version=str(raw.get("version", "unknown")),
                memory_gb=int(raw.get("memory_gb", 4)),
                port=int(raw.get("port", DEFAULT_SERVER_PORT)),
                rcon_port=int(raw.get("rcon_port", DEFAULT_RCON_PORT)),
            )
        )
    return sorted(server_instances, key=lambda item: item.name.lower())


def get_server(server_id: str) -> ServerInstance:
    clean_id = slugify_server_id(server_id)
    for server in list_servers():
        if server.server_id == clean_id:
            return server
    raise ServerManagerError(f"Server '{clean_id}' does not exist.")


def active_server_id() -> str | None:
    ensure_layout()
    if not ACTIVE_SERVER_FILE.exists():
        server_instances = list_servers()
        return server_instances[0].server_id if server_instances else None
    value = ACTIVE_SERVER_FILE.read_text(encoding="utf-8").strip()
    return value or None


def active_server() -> ServerInstance | None:
    server_id = active_server_id()
    return get_server(server_id) if server_id else None


def set_active_server(server_id: str) -> ServerInstance:
    server = get_server(server_id)
    ACTIVE_SERVER_FILE.write_text(server.server_id + "\n", encoding="utf-8")
    return server


def reserve_server(
    name: str,
    version: str,
    memory_gb: int,
    server_id: str | None = None,
) -> ServerInstance:
    clean_id = slugify_server_id(server_id or name)
    registry = _load_registry()
    if clean_id in registry["servers"] or server_directory(clean_id).exists():
        raise ServerManagerError(f"A server named '{clean_id}' already exists.")

    # MineBox intentionally runs only one Minecraft server at a time, so every
    # server can share Minecraft's default gameplay and RCON ports.
    instance = ServerInstance(
        server_id=clean_id,
        name=name.strip(),
        directory=str(server_directory(clean_id)),
        version=version,
        memory_gb=memory_gb,
        port=DEFAULT_SERVER_PORT,
        rcon_port=DEFAULT_RCON_PORT,
    )
    registry["servers"][clean_id] = asdict(instance)
    _save_registry(registry)

    if active_server_id() is None:
        set_active_server(clean_id)

    return instance


def normalize_shared_ports() -> int:
    """Set every registered server to MineBox's shared default ports."""
    registry = _load_registry()
    changed = 0
    for raw in registry["servers"].values():
        if raw.get("port") != DEFAULT_SERVER_PORT:
            raw["port"] = DEFAULT_SERVER_PORT
            changed += 1
        if raw.get("rcon_port") != DEFAULT_RCON_PORT:
            raw["rcon_port"] = DEFAULT_RCON_PORT
            changed += 1
    if changed:
        _save_registry(registry)
    return changed


def remove_server_record(server_id: str) -> None:
    clean_id = slugify_server_id(server_id)
    registry = _load_registry()
    registry["servers"].pop(clean_id, None)
    _save_registry(registry)
    if active_server_id() == clean_id:
        remaining = list_servers()
        if remaining:
            set_active_server(remaining[0].server_id)
        else:
            ACTIVE_SERVER_FILE.unlink(missing_ok=True)


def delete_server(server_id: str) -> ServerInstance:
    instance = get_server(server_id)
    directory = Path(instance.directory).resolve()
    servers_root = SERVERS_DIR.resolve()

    if directory.parent != servers_root:
        raise ServerManagerError(
            f"Refusing to delete server directory outside '{servers_root}'."
        )

    try:
        if directory.exists():
            shutil.rmtree(directory)
    except OSError as error:
        raise ServerManagerError(
            f"Could not delete the files for '{instance.name}': {error}"
        ) from error

    remove_server_record(instance.server_id)
    return instance
