from __future__ import annotations
import re
import time
from pathlib import Path
from config import SERVICE_NAME, SERVER_LOG, SERVER_PROPERTIES
from services.system import CommandResult, run
from services import rcon

def is_running() -> bool:
    return run(["systemctl", "is-active", SERVICE_NAME]).stdout == "active"

def _service(action: str) -> CommandResult:
    return run(["sudo", "-n", "/usr/bin/systemctl", action, SERVICE_NAME], timeout=45)

def wait_for_state(running: bool, timeout: int = 30) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if is_running() == running:
            return True
        time.sleep(0.5)
    return False

def start() -> CommandResult:
    if is_running():
        return CommandResult(True, "Minecraft is already running.")
    result = _service("start")
    if result.ok and not wait_for_state(True):
        return CommandResult(False, stderr="The service command succeeded, but Minecraft did not become active within 30 seconds.")
    return result

def save_world() -> CommandResult:
    if not is_running():
        return CommandResult(True, "Server is offline; no live world save was needed.")
    result = rcon.send("save-all flush")
    if not result.ok:
        return CommandResult(False, stderr=f"RCON save failed: {result.message}")
    return CommandResult(True, result.stdout or "World save requested.")

def stop() -> CommandResult:
    if not is_running():
        return CommandResult(True, "Minecraft is already offline.")
    saved = save_world()
    if not saved.ok:
        return saved
    result = _service("stop")
    if result.ok and not wait_for_state(False):
        return CommandResult(False, stderr="Minecraft did not stop within 30 seconds.")
    return result

def restart() -> CommandResult:
    if is_running():
        saved = save_world()
        if not saved.ok:
            return saved
    result = _service("restart")
    if result.ok and not wait_for_state(True):
        return CommandResult(False, stderr="Minecraft did not become active after restart.")
    return result

def status_text() -> str:
    return "Online" if is_running() else "Offline"

def player_info() -> tuple[list[str], int] | None:
    return rcon.players() if is_running() else None

def player_count_text() -> str:
    info = player_info()
    return f"{len(info[0])}/{info[1]}" if info else ("Offline" if not is_running() else "Unavailable")

def version() -> str:
    try:
        text = SERVER_LOG.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "Unknown"
    matches = re.findall(r"Starting minecraft server version ([^\s]+)", text, re.I)
    return matches[-1] if matches else "Unknown"

def uptime() -> str:
    if not is_running():
        return "Offline"
    result = run(["systemctl", "show", SERVICE_NAME, "--property=ActiveEnterTimestampMonotonic", "--value"])
    try:
        start_us = int(result.stdout)
        now = float(Path("/proc/uptime").read_text().split()[0])
        total = max(0, int(now - start_us / 1_000_000))
    except (ValueError, OSError, IndexError):
        return "Unknown"
    d, rem = divmod(total, 86400); h, rem = divmod(rem, 3600); m, s = divmod(rem, 60)
    return f"{d}d {h}h {m}m" if d else (f"{h}h {m}m" if h else f"{m}m {s}s")

def recent_logs(count: int = 20) -> list[str]:
    try:
        lines = SERVER_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
        return [x.strip() for x in lines[-count:] if x.strip()] or ["No recent server activity."]
    except OSError as exc:
        return [f"Unable to read log: {exc}"]

def read_properties() -> tuple[dict[str, str], str | None]:
    props: dict[str, str] = {}
    try:
        for raw in SERVER_PROPERTIES.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                props[key] = value
        return props, None
    except OSError as exc:
        return {}, str(exc)

def update_property(key: str, value: str) -> CommandResult:
    try:
        lines = SERVER_PROPERTIES.read_text(encoding="utf-8").splitlines()
        found = False
        output = []
        for line in lines:
            if not line.startswith("#") and line.split("=", 1)[0] == key:
                output.append(f"{key}={value}"); found = True
            else:
                output.append(line)
        if not found:
            output.append(f"{key}={value}")
        SERVER_PROPERTIES.write_text("\n".join(output) + "\n", encoding="utf-8")
        return CommandResult(True, f"{key} updated. Restart Minecraft to apply it.")
    except OSError as exc:
        return CommandResult(False, stderr=str(exc))
