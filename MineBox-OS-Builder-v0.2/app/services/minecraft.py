from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from pathlib import Path

from config import SERVICE_NAME
from services import rcon
from services import servers
from services.system import CommandResult, run


def _dev_mode() -> bool:
    return os.environ.get("MINEBOX_DEV_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _pid_file() -> Path:
    return servers.METADATA_DIR / "dev-server.pid"


def _active_server_dir() -> Path | None:
    active = servers.active_server()
    if active is None:
        return None
    return Path(active.directory)


def _server_log() -> Path:
    server_dir = _active_server_dir()
    if server_dir is not None:
        return server_dir / "logs" / "latest.log"
    return Path("/opt/minecraft/server/logs/latest.log")


def _server_properties() -> Path:
    server_dir = _active_server_dir()
    if server_dir is not None:
        return server_dir / "server.properties"
    return Path("/opt/minecraft/server/server.properties")


def _read_pid() -> int | None:
    path = _pid_file()
    if not path.is_file():
        return None
    try:
        value = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return value if value > 0 else None


def _write_pid(pid: int) -> None:
    servers.ensure_layout()
    _pid_file().write_text(f"{pid}\n", encoding="utf-8")


def _clear_pid() -> None:
    _pid_file().unlink(missing_ok=True)


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _dev_is_running() -> bool:
    pid = _read_pid()
    if pid is None:
        return False
    if not _pid_is_alive(pid):
        _clear_pid()
        return False
    return True


def is_running() -> bool:
    if _dev_mode():
        return _dev_is_running()
    return run(["systemctl", "is-active", SERVICE_NAME]).stdout == "active"


def _service(action: str) -> CommandResult:
    return run(
        ["sudo", "-n", "/usr/bin/systemctl", action, SERVICE_NAME],
        timeout=45,
    )


def wait_for_state(running: bool, timeout: int = 30) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if is_running() == running:
            return True
        time.sleep(0.5)
    return False


def _dev_start() -> CommandResult:
    if _dev_is_running():
        return CommandResult(True, "Minecraft is already running.")

    try:
        from services.launcher import build_command

        server_dir, command = build_command()
    except Exception as error:
        return CommandResult(False, stderr=str(error))

    server_jar = server_dir / "server.jar"
    start_script = server_dir / "start.sh"
    if not server_jar.is_file() and not start_script.is_file():
        return CommandResult(
            False,
            stderr=(
                f"Missing server.jar or start.sh in '{server_dir}'. "
                "Create or finish installing a Minecraft server first."
            ),
        )

    try:
        process = subprocess.Popen(
            command,
            cwd=server_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        return CommandResult(False, stderr=str(error))

    _write_pid(process.pid)
    if not wait_for_state(True, timeout=5):
        return CommandResult(
            False,
            stderr="Minecraft process exited immediately after start.",
        )
    return CommandResult(True, "Minecraft started in development mode.")


def _dev_stop() -> CommandResult:
    if not _dev_is_running():
        _clear_pid()
        return CommandResult(True, "Minecraft is already offline.")

    pid = _read_pid()
    if pid is None:
        return CommandResult(True, "Minecraft is already offline.")

    try:
        os.kill(pid, signal.SIGINT)
    except ProcessLookupError:
        _clear_pid()
        return CommandResult(True, "Minecraft is already offline.")
    except OSError as error:
        return CommandResult(False, stderr=str(error))

    if not wait_for_state(False, timeout=30):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        if not wait_for_state(False, timeout=10):
            return CommandResult(
                False,
                stderr="Minecraft did not stop within 40 seconds.",
            )

    _clear_pid()
    return CommandResult(True, "Minecraft stopped.")


def start() -> CommandResult:
    if is_running():
        return CommandResult(True, "Minecraft is already running.")
    if _dev_mode():
        return _dev_start()
    result = _service("start")
    if result.ok and not wait_for_state(True):
        return CommandResult(
            False,
            stderr=(
                "The service command succeeded, but Minecraft did not "
                "become active within 30 seconds."
            ),
        )
    return result


def save_world() -> CommandResult:
    if not is_running():
        return CommandResult(
            True,
            "Server is offline; no live world save was needed.",
        )
    result = rcon.send("save-all flush")
    if not result.ok:
        return CommandResult(
            False,
            stderr=f"RCON save failed: {result.message}",
        )
    return CommandResult(True, result.stdout or "World save requested.")


def stop() -> CommandResult:
    if not is_running():
        return CommandResult(True, "Minecraft is already offline.")
    # Best-effort flush; do not block stop if RCON is misconfigured.
    save_world()
    if _dev_mode():
        return _dev_stop()
    result = _service("stop")
    if result.ok and not wait_for_state(False):
        return CommandResult(
            False,
            stderr="Minecraft did not stop within 30 seconds.",
        )
    return result


def restart() -> CommandResult:
    if is_running():
        save_world()
    if _dev_mode():
        stopped = _dev_stop() if is_running() else CommandResult(True)
        if not stopped.ok:
            return stopped
        return _dev_start()
    result = _service("restart")
    if result.ok and not wait_for_state(True):
        return CommandResult(
            False,
            stderr="Minecraft did not become active after restart.",
        )
    return result


def status_text() -> str:
    return "Online" if is_running() else "Offline"


def player_info() -> tuple[list[str], int] | None:
    if not is_running():
        return None
    try:
        return rcon.players()
    except Exception:
        return None


def player_count_text() -> str:
    if not is_running():
        return "Offline"
    info = player_info()
    if info:
        return f"{len(info[0])}/{info[1]}"
    return "Unavailable"


def version() -> str:
    try:
        text = _server_log().read_text(encoding="utf-8", errors="ignore")
    except OSError:
        active = servers.active_server()
        return active.version if active else "Unknown"
    matches = re.findall(
        r"Starting minecraft server version ([^\s]+)",
        text,
        re.I,
    )
    if matches:
        return matches[-1]
    active = servers.active_server()
    return active.version if active else "Unknown"


def uptime() -> str:
    if not is_running():
        return "Offline"
    if _dev_mode():
        return "Running"
    result = run(
        [
            "systemctl",
            "show",
            SERVICE_NAME,
            "--property=ActiveEnterTimestampMonotonic",
            "--value",
        ]
    )
    try:
        start_us = int(result.stdout)
        now = float(Path("/proc/uptime").read_text().split()[0])
        total = max(0, int(now - start_us / 1_000_000))
    except (ValueError, OSError, IndexError):
        return "Unknown"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {seconds}s"


def recent_logs(count: int = 20) -> list[str]:
    try:
        lines = _server_log().read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines()
        cleaned = [line.strip() for line in lines[-count:] if line.strip()]
        return cleaned or ["No recent server activity."]
    except OSError as exc:
        return [f"Unable to read log: {exc}"]


_SETTINGS_BOOLEAN_KEYS = {
    "online-mode",
    "pvp",
    "white-list",
    "allow-flight",
    "enable-command-block",
    "force-gamemode",
}

_SETTINGS_INTEGER_KEYS = {
    "max-players",
    "view-distance",
    "simulation-distance",
    "server-port",
    "player-idle-timeout",
}

_SETTINGS_SELECT_KEYS = {
    "gamemode": {"survival", "creative", "adventure", "spectator"},
    "difficulty": {"peaceful", "easy", "normal", "hard"},
}

_SETTINGS_KEYS = (
    "motd",
    "max-players",
    "gamemode",
    "difficulty",
    "view-distance",
    "simulation-distance",
    "server-port",
    "player-idle-timeout",
    "online-mode",
    "pvp",
    "white-list",
    "allow-flight",
    "enable-command-block",
    "force-gamemode",
)


def read_properties() -> tuple[dict[str, str], str | None]:
    props: dict[str, str] = {}
    try:
        for raw in _server_properties().read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                props[key] = value
        return props, None
    except OSError as exc:
        return {}, str(exc)


def _parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def _format_setting_value(key: str, value: object) -> str:
    if key in _SETTINGS_BOOLEAN_KEYS:
        return "true" if _parse_bool(value) else "false"
    if key in _SETTINGS_INTEGER_KEYS:
        return str(int(value))  # type: ignore[arg-type]
    return str(value).strip()


def _normalize_settings(raw: dict[str, str]) -> dict[str, object]:
    """Convert server.properties strings into JSON-friendly values for the UI."""
    defaults: dict[str, object] = {
        "motd": "MineBox Minecraft Server",
        "max-players": 20,
        "gamemode": "survival",
        "difficulty": "peaceful",
        "view-distance": 10,
        "simulation-distance": 10,
        "server-port": 25565,
        "player-idle-timeout": 0,
        "online-mode": True,
        "pvp": True,
        "white-list": False,
        "allow-flight": False,
        "enable-command-block": False,
        "force-gamemode": False,
    }
    settings = dict(defaults)
    for key in _SETTINGS_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if key in _SETTINGS_BOOLEAN_KEYS:
            settings[key] = _parse_bool(value, bool(defaults[key]))
        elif key in _SETTINGS_INTEGER_KEYS:
            try:
                settings[key] = int(str(value).strip())
            except ValueError:
                settings[key] = defaults[key]
        else:
            settings[key] = value
    return settings


def read_server_settings() -> dict[str, object]:
    """API payload for GET /api/v1/minecraft/settings."""
    properties_path = _server_properties()
    props, error = read_properties()
    if error:
        return {
            "ok": False,
            "message": f"Unable to read server.properties: {error}",
            "path": str(properties_path),
            "settings": {},
        }
    return {
        "ok": True,
        "message": "Server settings loaded.",
        "path": str(properties_path),
        "settings": _normalize_settings(props),
        "restart_required": True,
    }


def _validate_settings_payload(
    settings: dict[str, object],
) -> dict[str, str]:
    errors: dict[str, str] = {}
    for key in _SETTINGS_KEYS:
        if key not in settings:
            continue
        value = settings[key]
        if key in _SETTINGS_BOOLEAN_KEYS:
            if not isinstance(value, bool) and str(value).lower() not in {
                "true",
                "false",
                "1",
                "0",
                "yes",
                "no",
                "on",
                "off",
            }:
                errors[key] = "Must be true or false."
            continue
        if key in _SETTINGS_INTEGER_KEYS:
            try:
                number = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                errors[key] = "Must be a whole number."
                continue
            ranges = {
                "max-players": (1, 1000),
                "view-distance": (2, 32),
                "simulation-distance": (2, 32),
                "server-port": (1024, 65535),
                "player-idle-timeout": (0, 1440),
            }
            low, high = ranges[key]
            if number < low or number > high:
                errors[key] = f"Must be between {low} and {high}."
            continue
        if key in _SETTINGS_SELECT_KEYS:
            allowed = _SETTINGS_SELECT_KEYS[key]
            if str(value).strip().lower() not in allowed:
                errors[key] = f"Must be one of: {', '.join(sorted(allowed))}."
            continue
        if key == "motd":
            text = str(value).strip()
            if not text:
                errors[key] = "MOTD cannot be empty."
            elif len(text) > 120:
                errors[key] = "MOTD must be 120 characters or fewer."
    return errors


def save_server_settings(payload: dict[str, object]) -> dict[str, object]:
    """API payload for PUT /api/v1/minecraft/settings.

    Minecraft rewrites server.properties from memory on shutdown. To make UI
    changes stick, stop the server first (if running), write the file, then
    start again when apply/restart was requested or the server was running.
    """
    raw_settings = payload.get("settings", payload)
    if not isinstance(raw_settings, dict):
        return {
            "ok": False,
            "status_code": 400,
            "message": "Settings payload must be an object.",
            "settings": {},
        }

    apply_changes = bool(payload.get("restart") or payload.get("apply"))
    errors = _validate_settings_payload(raw_settings)
    if errors:
        return {
            "ok": False,
            "status_code": 400,
            "message": "Correct the highlighted settings before saving.",
            "errors": errors,
            "settings": raw_settings,
        }

    properties_path = _server_properties()
    servers.ensure_layout()
    if not properties_path.is_file():
        return {
            "ok": False,
            "status_code": 500,
            "message": f"server.properties was not found at {properties_path}.",
            "path": str(properties_path),
            "settings": {},
        }

    formatted: dict[str, str] = {}
    for key in _SETTINGS_KEYS:
        if key not in raw_settings:
            continue
        value = _format_setting_value(key, raw_settings[key])
        if key in _SETTINGS_SELECT_KEYS:
            value = value.lower()
        formatted[key] = value

    was_running = is_running()
    if was_running:
        # Stop first so Minecraft's shutdown flush cannot overwrite our edits.
        stopped = stop()
        if not stopped.ok:
            return {
                "ok": False,
                "status_code": 500,
                "message": (
                    "Could not stop Minecraft to apply settings: "
                    f"{stopped.stderr or stopped.stdout}"
                ),
                "path": str(properties_path),
                "settings": {},
            }
        # Brief pause so the process fully releases the properties file.
        time.sleep(1.0)

    write_result = write_properties_updates(formatted)
    if not write_result.ok:
        # Try to bring the server back if we stopped it.
        if was_running:
            start()
        return {
            "ok": False,
            "status_code": 500,
            "message": write_result.stderr or "Could not write server.properties.",
            "path": str(properties_path),
            "settings": {},
        }

    # Keep the MineBox server registry in sync with the game port / MOTD.
    try:
        active = servers.active_server()
        if active is not None:
            registry = servers._load_registry()
            entry = registry.get("servers", {}).get(active.server_id)
            if isinstance(entry, dict):
                if "server-port" in formatted:
                    entry["port"] = int(formatted["server-port"])
                if "motd" in formatted and formatted["motd"].strip():
                    entry["name"] = formatted["motd"].strip()[:80]
                servers._save_registry(registry)
    except Exception:
        pass

    try:
        from services import join_access

        join_access.ensure_avahi_advertisement(
            int(formatted["server-port"])
            if "server-port" in formatted
            else None
        )
    except Exception:
        pass

    should_start = apply_changes or was_running
    started_ok = True
    start_message = ""
    if should_start:
        started = start()
        started_ok = bool(started.ok)
        start_message = started.stdout or started.stderr or ""

    current = read_server_settings()
    if not started_ok:
        return {
            "ok": False,
            "status_code": 500,
            "message": (
                "Settings were written, but Minecraft did not start: "
                f"{start_message}"
            ),
            "path": str(properties_path),
            "settings": current.get("settings", {}),
            "restart_required": False,
        }

    if was_running or apply_changes:
        message = "Settings saved and Minecraft restarted so they take effect."
    else:
        message = "Settings saved to server.properties."

    return {
        "ok": True,
        "message": message,
        "path": str(properties_path),
        "settings": current.get("settings", {}),
        "restart_required": False,
        "applied": bool(was_running or apply_changes),
    }


def write_properties_updates(updates: dict[str, str]) -> CommandResult:
    """Write many server.properties keys in a single pass."""
    properties_path = _server_properties()
    try:
        if properties_path.is_file():
            lines = properties_path.read_text(encoding="utf-8").splitlines()
        else:
            lines = []

        remaining = dict(updates)
        output: list[str] = []
        for line in lines:
            stripped = line.strip()
            if (
                stripped
                and not stripped.startswith("#")
                and "=" in stripped
            ):
                key = stripped.split("=", 1)[0]
                if key in remaining:
                    output.append(f"{key}={remaining.pop(key)}")
                    continue
            output.append(line)

        for key, value in remaining.items():
            output.append(f"{key}={value}")

        temporary = properties_path.with_suffix(".properties.minebox-tmp")
        temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
        temporary.replace(properties_path)

        # Verify the values we care about actually landed.
        written, error = read_properties()
        if error:
            return CommandResult(False, stderr=error)
        for key, value in updates.items():
            if written.get(key) != value:
                return CommandResult(
                    False,
                    stderr=(
                        f"server.properties did not keep {key}={value} "
                        f"(found {written.get(key)!r})."
                    ),
                )

        return CommandResult(
            True,
            "server.properties updated.",
        )
    except OSError as exc:
        return CommandResult(False, stderr=str(exc))


def update_property(key: str, value: str) -> CommandResult:
    return write_properties_updates({key: value})
