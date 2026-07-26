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
    saved = save_world()
    if not saved.ok:
        return saved
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
        saved = save_world()
        if not saved.ok:
            return saved
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


def update_property(key: str, value: str) -> CommandResult:
    properties_path = _server_properties()
    try:
        lines = properties_path.read_text(encoding="utf-8").splitlines()
        found = False
        output = []
        for line in lines:
            if not line.startswith("#") and line.split("=", 1)[0] == key:
                output.append(f"{key}={value}")
                found = True
            else:
                output.append(line)
        if not found:
            output.append(f"{key}={value}")
        properties_path.write_text(
            "\n".join(output) + "\n",
            encoding="utf-8",
        )
        return CommandResult(
            True,
            f"{key} updated. Restart Minecraft to apply it.",
        )
    except OSError as exc:
        return CommandResult(False, stderr=str(exc))
