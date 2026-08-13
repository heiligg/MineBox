from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services import minecraft
from services import rcon
from services import servers


class PlayersError(Exception):
    """User-facing player management failure."""


_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")


def _active_root() -> Path:
    active = servers.active_server()
    if active is None:
        raise PlayersError("No active Minecraft server is configured.")
    root = Path(active.directory).expanduser().resolve()
    if not root.is_dir():
        raise PlayersError(f"Server directory is missing: {root}")
    return root


def _validate_name(name: str) -> str:
    clean = (name or "").strip()
    if not _NAME_RE.fullmatch(clean):
        raise PlayersError(
            "Player names must be 1–16 characters (letters, numbers, underscore)."
        )
    return clean


def _offline_uuid(name: str) -> str:
    digest = hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest()
    return str(uuid.UUID(bytes=digest, version=3))


def _copy_player_file(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.resolve() == source.resolve():
        return
    if dest.is_file():
        backup = dest.with_name(dest.name + ".bak-uuid")
        if not backup.exists():
            shutil.copy2(dest, backup)
    shutil.copy2(source, dest)


def _player_names_and_uuids(root: Path) -> dict[str, set[str]]:
    names: dict[str, set[str]] = {}
    for entry in _read_json_list(root / "usercache.json"):
        name = entry.get("name")
        uid = entry.get("uuid")
        if not isinstance(name, str) or not isinstance(uid, str):
            continue
        clean = name.strip()
        if not clean:
            continue
        names.setdefault(clean, set()).add(uid.strip().lower())
    usernamecache = root / "usernamecache.json"
    if usernamecache.is_file():
        try:
            data = json.loads(usernamecache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            data = None
        if isinstance(data, dict):
            for uid, name in data.items():
                if not isinstance(uid, str) or not isinstance(name, str):
                    continue
                clean = name.strip()
                if not clean:
                    continue
                names.setdefault(clean, set()).add(uid.strip().lower())
    for name in list(names):
        names[name].add(_offline_uuid(name).lower())
    return names


def migrate_playerdata_for_online_mode(root: Path | None = None) -> list[str]:
    """Copy playerdata when online-mode flips a username onto a new UUID.

    Mojang (online) UUIDs and offline UUIDs are different files. Turning
    online-mode off otherwise makes the player join as a new empty character.
    """
    if root is None:
        try:
            root = _active_root()
        except PlayersError:
            return []
    world = root / "world"
    playerdata = world / "playerdata"
    if not playerdata.is_dir():
        return []

    online = True
    properties_path = root / "server.properties"
    if properties_path.is_file():
        try:
            for raw in properties_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line.lower().startswith("online-mode="):
                    online = line.split("=", 1)[1].strip().lower() == "true"
                    break
        except OSError:
            pass
    moved: list[str] = []
    sidecars = (
        (world / "stats", ".json"),
        (world / "advancements", ".json"),
    )

    for name, uuids in _player_names_and_uuids(root).items():
        files = [
            playerdata / f"{uid}.dat"
            for uid in uuids
            if (playerdata / f"{uid}.dat").is_file()
        ]
        if not files:
            continue
        best = max(files, key=lambda path: path.stat().st_size)
        offline = _offline_uuid(name).lower()
        if online:
            online_files = [path for path in files if path.stem.lower() != offline]
            target = online_files[0] if online_files else (playerdata / f"{best.stem}.dat")
            if best.stem.lower() != offline:
                target = best
        else:
            target = playerdata / f"{offline}.dat"
        if target.is_file() and target.stat().st_size >= best.stat().st_size:
            continue
        try:
            _copy_player_file(best, target)
            for folder, suffix in sidecars:
                source_side = folder / f"{best.stem}{suffix}"
                dest_side = folder / f"{target.stem}{suffix}"
                if source_side.is_file() and (
                    not dest_side.is_file()
                    or dest_side.stat().st_size < source_side.stat().st_size
                ):
                    _copy_player_file(source_side, dest_side)
        except OSError:
            continue
        moved.append(f"{name}:{best.stem}->{target.stem}")
    return moved


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _write_json_list(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")


def _names_from_entries(entries: list[dict[str, Any]], key: str = "name") -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        value = entry.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        name = value.strip()
        lower = name.lower()
        if lower in seen:
            continue
        seen.add(lower)
        names.append(name)
    return names


def _whitelist_enabled(root: Path) -> bool:
    props, _error = minecraft.read_properties()
    raw = props.get("white-list") or props.get("white_list") or "false"
    return str(raw).strip().lower() in {"true", "1", "yes", "on"}


def _set_whitelist_enabled(enabled: bool) -> None:
    root = _active_root()
    path = root / "server.properties"
    lines: list[str] = []
    found = False
    value = "true" if enabled else "false"
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise PlayersError(f"Could not update white-list: {exc}") from exc
    output: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("white-list=") or stripped.startswith("white_list="):
            output.append(f"white-list={value}")
            found = True
        else:
            output.append(raw.rstrip("\n"))
    if not found:
        output.append(f"white-list={value}")
    try:
        path.write_text("\n".join(output) + "\n", encoding="utf-8")
    except OSError as exc:
        raise PlayersError(f"Could not update white-list: {exc}") from exc


def _rcon(command: str) -> str:
    try:
        # Do not mirror player admin actions into the live console log.
        return rcon.command(command, mirror=False)
    except RuntimeError as error:
        raise PlayersError(str(error)) from error


def status() -> dict[str, Any]:
    root = _active_root()
    running = minecraft.is_running()
    online: list[str] = []
    max_players: int | None = None
    rcon_ok = False
    if running:
        info = minecraft.player_info()
        if info is not None:
            online, max_players = info
            rcon_ok = True

    ops = _names_from_entries(_read_json_list(root / "ops.json"))
    whitelist = _names_from_entries(_read_json_list(root / "whitelist.json"))
    bans = _names_from_entries(_read_json_list(root / "banned-players.json"))
    banned_ips = _names_from_entries(
        _read_json_list(root / "banned-ips.json"),
        key="ip",
    )

    return {
        "server_running": running,
        "rcon_available": rcon_ok,
        "online": online,
        "max_players": max_players,
        "ops": ops,
        "whitelist": whitelist,
        "bans": bans,
        "banned_ips": banned_ips,
        "whitelist_enabled": _whitelist_enabled(root),
    }


def _json_add_named(
    filename: str,
    name: str,
    *,
    extra: dict[str, Any] | None = None,
) -> None:
    root = _active_root()
    path = root / filename
    entries = _read_json_list(path)
    lower = name.lower()
    for entry in entries:
        existing = entry.get("name")
        if isinstance(existing, str) and existing.lower() == lower:
            return
    item: dict[str, Any] = {
        "uuid": _offline_uuid(name),
        "name": name,
    }
    if extra:
        item.update(extra)
    entries.append(item)
    _write_json_list(path, entries)


def _json_remove_named(filename: str, name: str) -> bool:
    root = _active_root()
    path = root / filename
    entries = _read_json_list(path)
    lower = name.lower()
    kept = [
        entry
        for entry in entries
        if not (
            isinstance(entry.get("name"), str)
            and entry["name"].lower() == lower
        )
    ]
    if len(kept) == len(entries):
        return False
    _write_json_list(path, kept)
    return True


def op_player(name: str) -> dict[str, Any]:
    name = _validate_name(name)
    if minecraft.is_running():
        _rcon(f"op {name}")
    else:
        _json_add_named(
            "ops.json",
            name,
            extra={"level": 4, "bypassesPlayerLimit": False},
        )
    return {"ok": True, "action": "op", "name": name, **status()}


def deop_player(name: str) -> dict[str, Any]:
    name = _validate_name(name)
    if minecraft.is_running():
        _rcon(f"deop {name}")
    else:
        _json_remove_named("ops.json", name)
    return {"ok": True, "action": "deop", "name": name, **status()}


def whitelist_add(name: str) -> dict[str, Any]:
    name = _validate_name(name)
    if minecraft.is_running():
        _rcon(f"whitelist add {name}")
    else:
        _json_add_named("whitelist.json", name)
    if not _whitelist_enabled(_active_root()):
        _set_whitelist_enabled(True)
        if minecraft.is_running():
            try:
                _rcon("whitelist on")
            except PlayersError:
                pass
    return {"ok": True, "action": "whitelist_add", "name": name, **status()}


def whitelist_remove(name: str) -> dict[str, Any]:
    name = _validate_name(name)
    if minecraft.is_running():
        _rcon(f"whitelist remove {name}")
    else:
        _json_remove_named("whitelist.json", name)
    return {"ok": True, "action": "whitelist_remove", "name": name, **status()}


def ban_player(name: str, reason: str = "") -> dict[str, Any]:
    name = _validate_name(name)
    reason = (reason or "").strip()[:200]
    if minecraft.is_running():
        command = f"ban {name}"
        if reason:
            command = f"{command} {reason}"
        _rcon(command)
    else:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %z")
        _json_add_named(
            "banned-players.json",
            name,
            extra={
                "created": now,
                "source": "MineBox",
                "expires": "forever",
                "reason": reason or "Banned by an operator.",
            },
        )
    return {"ok": True, "action": "ban", "name": name, **status()}


def pardon_player(name: str) -> dict[str, Any]:
    name = _validate_name(name)
    if minecraft.is_running():
        _rcon(f"pardon {name}")
    else:
        _json_remove_named("banned-players.json", name)
    return {"ok": True, "action": "pardon", "name": name, **status()}


def kick_player(name: str, reason: str = "") -> dict[str, Any]:
    name = _validate_name(name)
    if not minecraft.is_running():
        raise PlayersError("Start the Minecraft server before kicking a player.")
    reason = (reason or "").strip()[:200]
    command = f"kick {name}"
    if reason:
        command = f"{command} {reason}"
    _rcon(command)
    return {"ok": True, "action": "kick", "name": name, **status()}
