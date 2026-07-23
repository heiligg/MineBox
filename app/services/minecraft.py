from __future__ import annotations
import re
import time
from pathlib import Path
from config import SERVICE_NAME, SERVER_LOG, SERVER_PROPERTIES
from services.system import CommandResult, run
from services import rcon

def is_running() -> bool:
    result = run([
        "systemctl",
        "show",
        SERVICE_NAME,
        "--property=ActiveState",
        "--property=SubState",
        "--value",
    ])

    states = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    return states == ["active", "running"]

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
        return CommandResult(
            True,
            "Server is offline; no live world save was needed.",
        )

    try:
        response = rcon.command("save-all flush")
        return CommandResult(
            True,
            response or "World save requested.",
        )
    except Exception as exc:
        return CommandResult(
            False,
            stderr=f"RCON save failed: {exc}",
        )

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
    if not is_running():
        return None

    players_function = getattr(rcon, "players", None)

    if not callable(players_function):
        return None

    try:
        return players_function()
    except Exception:
        return None

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


# MineBox Server Settings API v1

_SERVER_SETTING_RULES = {
    "motd": {
        "type": "string",
        "minimum_length": 1,
        "maximum_length": 120,
    },
    "max-players": {
        "type": "integer",
        "minimum": 1,
        "maximum": 1000,
    },
    "difficulty": {
        "type": "choice",
        "choices": {
            "0": "peaceful",
            "1": "easy",
            "2": "normal",
            "3": "hard",
            "peaceful": "peaceful",
            "easy": "easy",
            "normal": "normal",
            "hard": "hard",
        },
        "stored_values": {
            "peaceful": "0",
            "easy": "1",
            "normal": "2",
            "hard": "3",
        },
    },
    "gamemode": {
        "type": "choice",
        "choices": {
            "0": "survival",
            "1": "creative",
            "2": "adventure",
            "3": "spectator",
            "survival": "survival",
            "creative": "creative",
            "adventure": "adventure",
            "spectator": "spectator",
        },
        "stored_values": {
            "survival": "0",
            "creative": "1",
            "adventure": "2",
            "spectator": "3",
        },
    },
    "online-mode": {
        "type": "boolean",
    },
    "pvp": {
        "type": "boolean",
    },
    "white-list": {
        "type": "boolean",
    },
    "allow-flight": {
        "type": "boolean",
    },
    "enable-command-block": {
        "type": "boolean",
    },
    "force-gamemode": {
        "type": "boolean",
    },
    "view-distance": {
        "type": "integer",
        "minimum": 2,
        "maximum": 32,
    },
    "simulation-distance": {
        "type": "integer",
        "minimum": 2,
        "maximum": 32,
    },
    "server-port": {
        "type": "integer",
        "minimum": 1024,
        "maximum": 65535,
    },
    "player-idle-timeout": {
        "type": "integer",
        "minimum": 0,
        "maximum": 1440,
    },
}


def _setting_boolean(value):
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()

    if normalized in {"true", "1", "yes", "on"}:
        return True

    if normalized in {"false", "0", "no", "off"}:
        return False

    raise ValueError("must be true or false")


def _display_setting_value(key: str, value: str):
    rule = _SERVER_SETTING_RULES[key]
    setting_type = rule["type"]

    if setting_type == "boolean":
        try:
            return _setting_boolean(value)
        except ValueError:
            return False

    if setting_type == "integer":
        try:
            return int(value)
        except (TypeError, ValueError):
            return rule.get("minimum", 0)

    if setting_type == "choice":
        normalized = str(value).strip().lower()
        return rule["choices"].get(normalized, normalized)

    return str(value)


def _validate_setting_value(key: str, value):
    rule = _SERVER_SETTING_RULES[key]
    setting_type = rule["type"]

    if setting_type == "boolean":
        parsed = _setting_boolean(value)
        return "true" if parsed else "false"

    if setting_type == "integer":
        if isinstance(value, bool):
            raise ValueError("must be a whole number")

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValueError("must be a whole number")

        minimum = rule["minimum"]
        maximum = rule["maximum"]

        if parsed < minimum or parsed > maximum:
            raise ValueError(
                f"must be between {minimum} and {maximum}"
            )

        return str(parsed)

    if setting_type == "choice":
        normalized = str(value).strip().lower()
        selected = rule["choices"].get(normalized)

        if selected is None:
            valid = sorted(set(rule["choices"].values()))
            raise ValueError(
                "must be one of: " + ", ".join(valid)
            )

        return rule["stored_values"].get(selected, selected)

    normalized = str(value).strip()

    minimum_length = rule.get("minimum_length", 0)
    maximum_length = rule.get("maximum_length", 1000)

    if len(normalized) < minimum_length:
        raise ValueError(
            f"must contain at least {minimum_length} character"
        )

    if len(normalized) > maximum_length:
        raise ValueError(
            f"must not exceed {maximum_length} characters"
        )

    if "\n" in normalized or "\r" in normalized:
        raise ValueError("must be entered on one line")

    return normalized


def read_server_settings() -> dict:
    properties, error = read_properties()

    if error:
        return {
            "ok": False,
            "message": (
                "MineBox could not read server.properties: "
                + error
            ),
            "settings": {},
        }

    settings = {}

    for key in _SERVER_SETTING_RULES:
        if key in properties:
            settings[key] = _display_setting_value(
                key,
                properties[key],
            )

    return {
        "ok": True,
        "settings": settings,
        "restart_required": False,
        "server_running": is_running(),
    }


def save_server_settings(payload) -> dict:
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status_code": 400,
            "message": "The settings request must be an object.",
            "errors": {
                "settings": "Invalid settings request."
            },
        }

    submitted = payload.get("settings", payload)

    if not isinstance(submitted, dict):
        return {
            "ok": False,
            "status_code": 400,
            "message": "The settings field must be an object.",
            "errors": {
                "settings": "Invalid settings request."
            },
        }

    if not submitted:
        return {
            "ok": False,
            "status_code": 400,
            "message": "No settings were provided.",
            "errors": {
                "settings": "Choose at least one setting to save."
            },
        }

    unknown = sorted(
        key
        for key in submitted
        if key not in _SERVER_SETTING_RULES
    )

    if unknown:
        return {
            "ok": False,
            "status_code": 400,
            "message": "Unsupported settings were provided.",
            "errors": {
                key: "This setting is not supported by MineBox."
                for key in unknown
            },
        }

    validated = {}
    errors = {}

    for key, value in submitted.items():
        try:
            validated[key] = _validate_setting_value(
                key,
                value,
            )
        except ValueError as exc:
            errors[key] = str(exc)

    if errors:
        return {
            "ok": False,
            "status_code": 422,
            "message": "Some settings are invalid.",
            "errors": errors,
        }

    try:
        original_text = SERVER_PROPERTIES.read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        return {
            "ok": False,
            "status_code": 500,
            "message": (
                "MineBox could not read server.properties: "
                + str(exc)
            ),
            "errors": {},
        }

    import shutil
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    backup_path = SERVER_PROPERTIES.with_name(
        f"{SERVER_PROPERTIES.name}.minebox-{timestamp}.bak"
    )

    try:
        shutil.copy2(
            SERVER_PROPERTIES,
            backup_path,
        )
    except OSError as exc:
        return {
            "ok": False,
            "status_code": 500,
            "message": (
                "MineBox could not create a settings backup: "
                + str(exc)
            ),
            "errors": {},
        }

    output = []
    updated_keys = set()

    for line in original_text.splitlines():
        if (
            line
            and not line.startswith("#")
            and "=" in line
        ):
            key = line.split("=", 1)[0]

            if key in validated:
                output.append(f"{key}={validated[key]}")
                updated_keys.add(key)
                continue

        output.append(line)

    for key, value in validated.items():
        if key not in updated_keys:
            output.append(f"{key}={value}")

    try:
        SERVER_PROPERTIES.write_text(
            "\n".join(output) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        try:
            shutil.copy2(
                backup_path,
                SERVER_PROPERTIES,
            )
        except OSError:
            pass

        return {
            "ok": False,
            "status_code": 500,
            "message": (
                "MineBox could not save server.properties: "
                + str(exc)
            ),
            "errors": {},
        }

    current = read_server_settings()

    return {
        "ok": True,
        "message": (
            "Server settings saved. Restart Minecraft "
            "to apply the changes."
        ),
        "settings": current.get("settings", {}),
        "changed": sorted(validated),
        "restart_required": True,
        "server_running": is_running(),
        "backup_file": backup_path.name,
    }

