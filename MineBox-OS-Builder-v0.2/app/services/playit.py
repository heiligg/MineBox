"""playit.gg tunnel for internet Minecraft joins without port forwarding."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from services.system import run


DATA_DIR = Path(os.environ.get("MINEBOX_PLAYIT_DIR", "/var/lib/minebox/playit"))
CONFIG_FILE = DATA_DIR / "playit.toml"
LOG_FILE = DATA_DIR / "playit.log"
HELPER = Path("/opt/minebox/scripts/minebox_playit.py")
API = "https://api.playit.gg"
CLAIM_RE = re.compile(r"https://playit\.gg/claim/[A-Za-z0-9/_-]+")
SECRET_RE = re.compile(r'secret_key\s*=\s*"([^"]+)"')
ADDRESS_RE = re.compile(
    r"[a-z0-9][a-z0-9.-]*\.(?:gl\.)?join\.playit\.gg(?::\d+)?",
    re.IGNORECASE,
)


def _helper(action: str, timeout: int = 180):
    command = ["sudo", "-n", "/usr/bin/python3", str(HELPER), action]
    if not HELPER.is_file():
        local = Path(__file__).resolve().parent.parent / "scripts" / "minebox_playit.py"
        command = ["sudo", "-n", "/usr/bin/python3", str(local), action]
    return run(command, timeout=timeout)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def secret_key() -> str | None:
    match = SECRET_RE.search(_read_text(CONFIG_FILE))
    if match:
        return match.group(1).strip() or None
    return None


def claim_url() -> str | None:
    found = CLAIM_RE.findall(_read_text(LOG_FILE))
    return found[-1] if found else None


def _unwrap(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    if payload.get("status") in {"success", "ok"}:
        return payload.get("data", payload)
    if "data" in payload and "error" not in payload:
        return payload.get("data")
    return payload


def _api(path: str, body: dict[str, Any], secret: str) -> Any:
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MineBox",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"error": str(exc)}
    try:
        return _unwrap(json.loads(raw) if raw else {})
    except json.JSONDecodeError:
        return {"error": raw[:200]}


def _collect_addresses(payload: Any) -> list[str]:
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key in (
                "display_address",
                "assigned_domain",
                "custom_domain",
                "name",
            ):
                text = str(value.get(key) or "").strip()
                if ADDRESS_RE.fullmatch(text) or (
                    text.endswith("playit.gg") and "." in text
                ):
                    found.append(text)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            found.extend(ADDRESS_RE.findall(value))

    walk(payload)
    unique: list[str] = []
    for address in found:
        if address not in unique:
            unique.append(address)
    return unique


def _ensure_minecraft_tunnel(secret: str, port: int) -> None:
    listed = _api("/tunnels/list", {}, secret)
    addresses = _collect_addresses(listed)
    if addresses:
        return
    rundata = _api("/agents/rundata", {}, secret)
    if _collect_addresses(rundata):
        return
    _api(
        "/tunnels/create",
        {
            "name": "MineBox Minecraft",
            "tunnel_type": "minecraft-java",
            "port_type": "tcp",
            "port_count": 1,
            "origin": {
                "type": "default",
                "data": {"local_ip": "127.0.0.1", "local_port": port},
            },
            "enabled": True,
        },
        secret,
    )
    _api(
        "/tunnels/create",
        {
            "name": "MineBox Voice Chat",
            "port_type": "udp",
            "port_count": 1,
            "origin": {
                "type": "default",
                "data": {"local_ip": "127.0.0.1", "local_port": 24454},
            },
            "enabled": True,
        },
        secret,
    )


def _join_address(secret: str | None) -> str | None:
    if secret:
        for path in ("/v1/agents/rundata", "/agents/rundata", "/tunnels/list"):
            addresses = _collect_addresses(_api(path, {}, secret))
            if addresses:
                return addresses[0]
    log_hits = ADDRESS_RE.findall(_read_text(LOG_FILE))
    return log_hits[-1] if log_hits else None


def _agent_running() -> bool:
    result = run(
        ["systemctl", "is-active", "minebox-playit.service"],
        timeout=10,
    )
    return result.stdout.strip() == "active"


def status() -> dict[str, Any]:
    secret = secret_key()
    running = _agent_running()
    claim = None if secret else claim_url()
    address = _join_address(secret) if running else None
    if running and secret and address:
        state = "connected"
        message = f"Friends can join Minecraft with {address}."
    elif running and claim:
        state = "needs_claim"
        message = (
            "playit.gg is running. Open the claim link once to connect this MineBox, "
            "then come back here."
        )
    elif running:
        state = "waiting"
        message = (
            "playit.gg is starting. If a claim link appears, open it. "
            "Otherwise wait a few seconds and refresh."
        )
    else:
        state = "stopped"
        message = (
            "Easy internet join uses playit.gg so friends do not need router settings."
        )
    return {
        "ok": True,
        "provider": "playit",
        "running": running,
        "claimed": bool(secret),
        "state": state,
        "claim_url": claim,
        "address": address,
        "message": message,
    }


def enable() -> dict[str, Any]:
    result = _helper("ensure", timeout=180)
    if not result.ok:
        return {
            **status(),
            "ok": False,
            "message": (
                "Could not start playit.gg. "
                + (result.message or "The install helper failed.")
            )[:400],
        }
    deadline = time.time() + 25
    current = status()
    while time.time() < deadline:
        current = status()
        if current.get("claim_url") or current.get("address") or current.get("claimed"):
            break
        time.sleep(1)
        current = status()
    secret = secret_key()
    if secret:
        try:
            from services import join_access

            _ensure_minecraft_tunnel(secret, join_access.game_port())
        except Exception:
            _ensure_minecraft_tunnel(secret, 25565)
        current = status()
    current["ok"] = True
    return current


def disable() -> dict[str, Any]:
    result = _helper("disable", timeout=30)
    current = status()
    current["ok"] = bool(result.ok)
    current["message"] = (
        "playit.gg internet join stopped."
        if result.ok
        else (result.message or "Could not stop playit.gg.")
    )
    return current
