from __future__ import annotations
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from config import SERVICE_NAME
from services.system import CommandResult, run
from services import rcon, servers

DEV_MODE = os.environ.get("MINEBOX_DEV_MODE", "0") == "1"


def _active_dir() -> Path:
    instance = servers.active_server()
    if instance is not None:
        return Path(instance.directory)
    return servers.MINECRAFT_ROOT / "server"


def _properties_path() -> Path:
    return _active_dir() / "server.properties"


def _log_path() -> Path:
    return _active_dir() / "logs" / "latest.log"


def _pid_path() -> Path:
    return _active_dir() / ".minebox-server.pid"


def _read_pid() -> int | None:
    try:
        return int(_pid_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_running() -> bool:
    if DEV_MODE:
        pid = _read_pid()
        if pid and _pid_running(pid):
            return True
        _pid_path().unlink(missing_ok=True)
        return False
    return run(["systemctl", "is-active", SERVICE_NAME]).stdout == "active"


def _service(action: str) -> CommandResult:
    return run(["sudo", "-n", "/usr/bin/systemctl", action, SERVICE_NAME], timeout=45)


def _dev_start() -> CommandResult:
    server_dir = _active_dir()
    jar = server_dir / "server.jar"
    start_script = server_dir / "start.sh"
    if not jar.is_file():
        return CommandResult(False, stderr=f"No server.jar was found in {server_dir}. Create a server first.")
    if not start_script.is_file():
        return CommandResult(False, stderr=f"No start.sh was found in {server_dir}.")
    try:
        log_dir = server_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        console_log = log_dir / "minebox-console.log"
        log_handle = console_log.open("ab", buffering=0)
        process = subprocess.Popen(
            [str(start_script)],
            cwd=server_dir,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        _pid_path().write_text(str(process.pid) + "\n", encoding="utf-8")
        time.sleep(1)
        if process.poll() is not None:
            _pid_path().unlink(missing_ok=True)
            return CommandResult(False, stderr=f"Minecraft exited immediately. Check {console_log}.")
        return CommandResult(True, f"Minecraft started with PID {process.pid}.")
    except OSError as exc:
        return CommandResult(False, stderr=f"Could not start Minecraft: {exc}")


def _dev_stop() -> CommandResult:
    pid = _read_pid()
    if not pid or not _pid_running(pid):
        _pid_path().unlink(missing_ok=True)
        return CommandResult(True, "Minecraft is already offline.")
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        _pid_path().unlink(missing_ok=True)
        return CommandResult(True, "Minecraft is already offline.")
    except OSError as exc:
        return CommandResult(False, stderr=f"Could not stop Minecraft: {exc}")
    end = time.monotonic() + 20
    while time.monotonic() < end:
        if not _pid_running(pid):
            _pid_path().unlink(missing_ok=True)
            return CommandResult(True, "Minecraft stopped.")
        time.sleep(0.5)
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass
    _pid_path().unlink(missing_ok=True)
    return CommandResult(True, "Minecraft was force-stopped after waiting 20 seconds.")


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
    if DEV_MODE:
        return _dev_start()
    result = _service("start")
    if result.ok and not wait_for_state(True):
        return CommandResult(False, stderr="The service command succeeded, but Minecraft did not become active within 30 seconds.")
    return result


def save_world() -> CommandResult:
    if not is_running():
        return CommandResult(True, "Server is offline; no live world save was needed.")
    result = rcon.send("save-all flush")
    if not result.ok:
        # During local development RCON may not be ready yet. Stopping should
        # still work instead of turning this into an HTTP 500.
        if DEV_MODE:
            return CommandResult(True, "RCON was unavailable; continuing with local shutdown.")
        return CommandResult(False, stderr=f"RCON save failed: {result.message}")
    return CommandResult(True, result.stdout or "World save requested.")


def stop() -> CommandResult:
    if not is_running():
        return CommandResult(True, "Minecraft is already offline.")
    saved = save_world()
    if not saved.ok:
        return saved
    if DEV_MODE:
        return _dev_stop()
    result = _service("stop")
    if result.ok and not wait_for_state(False):
        return CommandResult(False, stderr="Minecraft did not stop within 30 seconds.")
    return result


def restart() -> CommandResult:
    if DEV_MODE:
        stopped = stop()
        if not stopped.ok:
            return stopped
        return start()
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
    if not is_running():
        return None
    try:
        return rcon.players()
    except Exception:
        # Status polling must never turn a successful start into HTTP 500.
        return None


def player_count_text() -> str:
    info = player_info()
    return f"{len(info[0])}/{info[1]}" if info else ("Offline" if not is_running() else "Unavailable")


def version() -> str:
    try:
        text = _log_path().read_text(encoding="utf-8", errors="ignore")
    except OSError:
        active = servers.active_server()
        return active.version if active else "Unknown"
    matches = re.findall(r"Starting minecraft server version ([^\s]+)", text, re.I)
    return matches[-1] if matches else ((servers.active_server().version) if servers.active_server() else "Unknown")


def uptime() -> str:
    if not is_running():
        return "Offline"
    if DEV_MODE:
        pid = _read_pid()
        if not pid:
            return "Unknown"
        try:
            age = time.time() - Path(f"/proc/{pid}").stat().st_ctime
            total = max(0, int(age))
        except OSError:
            return "Unknown"
    else:
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
    for path in (_log_path(), _active_dir() / "logs" / "minebox-console.log"):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if lines:
                return [x.strip() for x in lines[-count:] if x.strip()]
        except OSError:
            continue
    return ["No recent server activity."]

def read_properties() -> tuple[dict[str, str], str | None]:
    props: dict[str, str] = {}
    try:
        for raw in _properties_path().read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                props[key] = value
        return props, None
    except OSError as exc:
        return {}, str(exc)

def update_property(key: str, value: str) -> CommandResult:
    try:
        lines = _properties_path().read_text(encoding="utf-8").splitlines()
        found = False
        output = []
        for line in lines:
            if not line.startswith("#") and line.split("=", 1)[0] == key:
                output.append(f"{key}={value}"); found = True
            else:
                output.append(line)
        if not found:
            output.append(f"{key}={value}")
        _properties_path().write_text("\n".join(output) + "\n", encoding="utf-8")
        return CommandResult(True, f"{key} updated. Restart Minecraft to apply it.")
    except OSError as exc:
        return CommandResult(False, stderr=str(exc))

# Dashboard server-settings support.
# These helpers intentionally live in this service so both the API and the
# built MineBox image use the same server.properties implementation.
_SETTING_RULES = {
    "motd": (str, None, None),
    "max-players": (int, 1, 1000),
    "gamemode": (str, None, None),
    "difficulty": (str, None, None),
    "view-distance": (int, 2, 32),
    "simulation-distance": (int, 2, 32),
    "server-port": (int, 1024, 65535),
    "player-idle-timeout": (int, 0, 1440),
    "online-mode": (bool, None, None),
    "pvp": (bool, None, None),
    "white-list": (bool, None, None),
    "allow-flight": (bool, None, None),
    "enable-command-block": (bool, None, None),
    "force-gamemode": (bool, None, None),
}

_ALLOWED_VALUES = {
    "gamemode": {"survival", "creative", "adventure", "spectator"},
    "difficulty": {"peaceful", "easy", "normal", "hard"},
}


def _to_dashboard_value(key: str, raw: str):
    expected_type = _SETTING_RULES[key][0]
    if expected_type is bool:
        return raw.strip().lower() == "true"
    if expected_type is int:
        try:
            return int(raw)
        except ValueError:
            return 0
    return raw


def read_server_settings() -> dict:
    properties, error = read_properties()
    if error:
        return {
            "ok": False,
            "message": f"Could not read server.properties: {error}",
        }

    settings = {}
    for key in _SETTING_RULES:
        if key in properties:
            settings[key] = _to_dashboard_value(key, properties[key])

    return {
        "ok": True,
        "settings": settings,
        "message": "Server settings loaded.",
    }


def _validate_setting(key: str, value):
    expected_type, minimum, maximum = _SETTING_RULES[key]

    if expected_type is bool:
        if not isinstance(value, bool):
            return None, "Must be true or false."
        return "true" if value else "false", None

    if expected_type is int:
        if isinstance(value, bool):
            return None, "Must be a number."
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None, "Must be a number."
        if minimum is not None and parsed < minimum:
            return None, f"Must be at least {minimum}."
        if maximum is not None and parsed > maximum:
            return None, f"Must be no more than {maximum}."
        return str(parsed), None

    parsed = str(value).strip()
    if key == "motd" and not parsed:
        return None, "Server name cannot be empty."
    if key == "motd" and len(parsed) > 120:
        return None, "Server name must be 120 characters or fewer."
    if key in _ALLOWED_VALUES and parsed not in _ALLOWED_VALUES[key]:
        return None, "Choose one of the available values."
    return parsed, None


def save_server_settings(payload: dict) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("settings"), dict):
        return {
            "ok": False,
            "status_code": 400,
            "message": "A settings object is required.",
            "errors": {},
        }

    requested = payload["settings"]
    errors = {}
    validated = {}

    for key, value in requested.items():
        if key not in _SETTING_RULES:
            continue
        normalized, error = _validate_setting(key, value)
        if error:
            errors[key] = error
        else:
            validated[key] = normalized

    if errors:
        return {
            "ok": False,
            "status_code": 422,
            "message": "One or more settings are invalid.",
            "errors": errors,
        }

    if not validated:
        return {
            "ok": False,
            "status_code": 400,
            "message": "No supported server settings were supplied.",
            "errors": {},
        }

    properties, error = read_properties()
    if error:
        return {
            "ok": False,
            "status_code": 500,
            "message": f"Could not read server.properties: {error}",
            "errors": {},
        }

    properties.update(validated)

    try:
        existing_lines = _properties_path().read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines()

        output = []
        written = set()
        for line in existing_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in line:
                key = line.split("=", 1)[0]
                if key in validated:
                    output.append(f"{key}={validated[key]}")
                    written.add(key)
                    continue
            output.append(line)

        for key, value in validated.items():
            if key not in written:
                output.append(f"{key}={value}")

        _properties_path().write_text(
            "\n".join(output).rstrip() + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return {
            "ok": False,
            "status_code": 500,
            "message": f"Could not save server.properties: {exc}",
            "errors": {},
        }

    return {
        "ok": True,
        "settings": {
            key: _to_dashboard_value(key, value)
            for key, value in validated.items()
        },
        "message": "Settings saved. Restart Minecraft to apply them.",
    }
