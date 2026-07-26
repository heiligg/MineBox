from __future__ import annotations

import platform
import socket
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from config import SERVICE_NAME
from services.system import run


@dataclass
class Sample:
    timestamp: float
    cpu: float
    memory: float
    server_memory_mb: float


_HISTORY: deque[Sample] = deque(maxlen=60)


def _read_total_cpu() -> tuple[int, int]:
    values = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
    nums = [int(value) for value in values]
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    return idle, sum(nums)


def _meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0])
    return values


def _memory_percent() -> float:
    values = _meminfo()
    total = values.get("MemTotal", 1)
    available = values.get("MemAvailable", 0)
    return round((total - available) * 100 / total, 1)


def server_process_memory_mb() -> float:
    result = run(
        ["systemctl", "show", SERVICE_NAME, "--property=MainPID", "--value"]
    )
    try:
        pid = int(result.stdout)
        if pid <= 0:
            return 0.0
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def sample() -> Sample:
    try:
        idle1, total1 = _read_total_cpu()
        time.sleep(0.08)
        idle2, total2 = _read_total_cpu()
        delta = max(1, total2 - total1)
        cpu = round(100 * (1 - (idle2 - idle1) / delta), 1)
    except (OSError, ValueError, IndexError):
        cpu = 0.0
    try:
        memory = _memory_percent()
    except (OSError, ValueError, IndexError):
        memory = 0.0
    item = Sample(time.time(), cpu, memory, server_process_memory_mb())
    _HISTORY.append(item)
    return item


def history() -> list[Sample]:
    return list(_HISTORY)


def _hostname() -> str:
    try:
        return socket.gethostname() or "Unknown"
    except OSError:
        return "Unknown"


def _ip_address() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.connect(("8.8.8.8", 80))
            address = sock.getsockname()[0]
            if address and not address.startswith("127."):
                return address
    except OSError:
        pass

    result = run(
        ["ip", "-4", "-o", "addr", "show", "scope", "global"]
    )
    if result.ok:
        preferred: list[str] = []
        others: list[str] = []
        for line in result.stdout.splitlines():
            # Example: 2: eth0    inet 192.168.0.106/24 ...
            parts = line.split()
            if len(parts) < 4 or parts[2] != "inet":
                continue
            address = parts[3].split("/", 1)[0]
            if address.startswith("127.") or address.startswith("169.254."):
                continue
            interface = parts[1].rstrip(":")
            if interface.startswith(("eth", "en", "end")):
                preferred.append(address)
            elif not interface.startswith("wlan") or not address.startswith(
                "192.168.4."
            ):
                others.append(address)
            else:
                others.append(address)
        if preferred:
            return preferred[0]
        if others:
            return others[0]

    try:
        for info in socket.getaddrinfo(_hostname(), None, socket.AF_INET):
            address = info[4][0]
            if not address.startswith("127."):
                return address
    except OSError:
        pass
    return None


def _system_uptime() -> str:
    try:
        total_seconds = int(
            float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        )
    except (OSError, ValueError, IndexError):
        return "Unavailable"

    days, remaining = divmod(total_seconds, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, _ = divmod(remaining, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _os_release() -> tuple[str | None, str | None]:
    name: str | None = None
    version: str | None = None
    path = Path("/etc/os-release")
    try:
        values: dict[str, str] = {}
        for raw in path.read_text(encoding="utf-8").splitlines():
            if "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            values[key] = value.strip().strip('"')
        name = values.get("PRETTY_NAME") or values.get("NAME")
        version = values.get("VERSION_ID") or values.get("VERSION")
    except OSError:
        pass
    if not name:
        name = platform.system() or None
    if not version:
        version = platform.release() or None
    return name, version


def _cpu_temperature_c() -> float | None:
    candidates = [
        Path("/sys/class/thermal/thermal_zone0/temp"),
        Path("/sys/class/hwmon/hwmon0/temp1_input"),
    ]
    for path in candidates:
        try:
            raw = int(path.read_text(encoding="utf-8").strip())
            # thermal_zone is millidegrees; some hwmon sensors are too
            celsius = raw / 1000.0 if raw > 200 else float(raw)
            if 0.0 < celsius < 150.0:
                return round(celsius, 1)
        except (OSError, ValueError):
            continue
    return None


def _read_sysfs_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _hwmon_fan_nodes() -> list[Path]:
    nodes: list[Path] = []
    platform_fan = Path("/sys/devices/platform/cooling_fan")
    if platform_fan.is_dir():
        nodes.extend(sorted(platform_fan.glob("hwmon/hwmon*")))
    class_hwmon = Path("/sys/class/hwmon")
    if class_hwmon.is_dir():
        for hwmon in sorted(class_hwmon.glob("hwmon*")):
            if hwmon in nodes:
                continue
            name_path = hwmon / "name"
            try:
                name = (
                    name_path.read_text(encoding="utf-8").strip().lower()
                    if name_path.is_file()
                    else ""
                )
            except OSError:
                name = ""
            if "fan" in name or (hwmon / "fan1_input").is_file():
                nodes.append(hwmon)
    return nodes


def _cooling_fan_devices() -> list[Path]:
    thermal = Path("/sys/class/thermal")
    if not thermal.is_dir():
        return []
    devices: list[Path] = []
    for device in sorted(thermal.glob("cooling_device*")):
        type_path = device / "type"
        try:
            dtype = (
                type_path.read_text(encoding="utf-8").strip().lower()
                if type_path.is_file()
                else ""
            )
        except OSError:
            dtype = ""
        if "fan" in dtype:
            devices.append(device)
    return devices


def fan_status() -> dict[str, float | int | str | bool | None]:
    """Read Pi 5 Active Cooler / firmware fan state from sysfs."""
    rpm: int | None = None
    pwm: int | None = None
    state: int | None = None
    max_state: int | None = None
    available = False

    for hwmon in _hwmon_fan_nodes():
        fan_input = hwmon / "fan1_input"
        if fan_input.is_file():
            available = True
            value = _read_sysfs_int(fan_input)
            if value is not None:
                rpm = value
        pwm_path = hwmon / "pwm1"
        if pwm_path.is_file():
            available = True
            value = _read_sysfs_int(pwm_path)
            if value is not None:
                pwm = value
        if rpm is not None or pwm is not None:
            break

    for device in _cooling_fan_devices():
        available = True
        state = _read_sysfs_int(device / "cur_state")
        max_state = _read_sysfs_int(device / "max_state")
        break

    if not available:
        status = "unavailable"
    elif (
        (rpm is not None and rpm > 0)
        or (pwm is not None and pwm > 0)
        or (state is not None and state > 0)
    ):
        status = "spinning"
    else:
        status = "off"

    return {
        "fan_available": available,
        "fan_rpm": rpm,
        "fan_pwm": pwm,
        "fan_state": state,
        "fan_max_state": max_state,
        "fan_status": status,
    }


def run_fan_test(duration_seconds: int = 8) -> dict[str, float | int | str | bool | None]:
    """Force the cooler to max briefly so users can verify hardware."""
    import subprocess

    duration_seconds = max(3, min(int(duration_seconds), 20))
    before = fan_status()
    if not before.get("fan_available"):
        raise RuntimeError(
            "No cooling fan was detected. Check that the Active Cooler "
            "is seated on the Pi 5 fan connector."
        )

    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "minebox_fan_test.py"
    )
    # Must run via sudo — sysfs cooling controls are root-only.
    # Prefer the installed helper; fall back to the OTA script path.
    commands = [
        [
            "sudo",
            "-n",
            "/usr/local/sbin/minebox-fan-test",
            "--seconds",
            str(duration_seconds),
        ],
        [
            "sudo",
            "-n",
            "/usr/bin/python3",
            "/opt/minebox/scripts/minebox_fan_test.py",
            "--seconds",
            str(duration_seconds),
        ],
    ]
    if script.is_file() and script.resolve() != Path(
        "/opt/minebox/scripts/minebox_fan_test.py"
    ).resolve():
        commands.append(
            [
                "sudo",
                "-n",
                "/usr/bin/python3",
                str(script),
                "--seconds",
                str(duration_seconds),
            ]
        )

    last_error = "Fan test failed."
    ran = False
    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=duration_seconds + 15,
            )
        except (OSError, subprocess.SubprocessError) as error:
            last_error = str(error)
            continue
        if result.returncode == 0:
            ran = True
            break
        detail = (result.stderr or result.stdout or "").strip()
        if "password is required" in detail.lower() or "a password is required" in detail.lower():
            last_error = (
                "Fan test needs root via sudoers. Install the latest "
                "MineBox update, then try again."
            )
        else:
            last_error = detail or f"Command failed ({result.returncode})."

    if not ran:
        raise RuntimeError(last_error)

    after = fan_status()
    return {
        "ok": True,
        "message": (
            "Fan test finished. The cooler should have spun at full speed "
            "for a few seconds. If you heard nothing, reseat the Active "
            "Cooler cable on the Pi 5 fan header."
        ),
        "before": before,
        "after": after,
        "duration_seconds": duration_seconds,
        **after,
    }


def system_status() -> dict[str, float | str | None]:
    """API-friendly system snapshot used by /api/v1/status."""
    sample_item = sample()
    memory_total_mb = 0.0
    memory_available_mb = 0.0
    memory_used_mb = 0.0
    try:
        values = _meminfo()
        memory_total_mb = round(values.get("MemTotal", 0) / 1024, 1)
        memory_available_mb = round(values.get("MemAvailable", 0) / 1024, 1)
        memory_used_mb = round(
            max(0.0, memory_total_mb - memory_available_mb),
            1,
        )
    except (OSError, ValueError, IndexError):
        pass

    disk_percent = 0.0
    disk_total_gb = 0.0
    disk_used_gb = 0.0
    disk_free_gb = 0.0
    try:
        import shutil

        usage = shutil.disk_usage("/")
        if usage.total:
            disk_percent = round((usage.used / usage.total) * 100, 1)
            disk_total_gb = round(usage.total / (1024**3), 1)
            disk_used_gb = round(usage.used / (1024**3), 1)
            disk_free_gb = round(usage.free / (1024**3), 1)
    except OSError:
        pass

    hostname = _hostname()
    temperature_c = _cpu_temperature_c()
    os_name, os_version = _os_release()
    minecraft_memory = sample_item.server_memory_mb

    temperature_text = "Unavailable"
    if temperature_c is not None:
        temperature_text = f"{temperature_c:.1f} C"

    fan = fan_status()

    return {
        "cpu_percent": sample_item.cpu,
        "memory_percent": sample_item.memory,
        "disk_percent": disk_percent,
        "temperature": temperature_text,
        "cpu_temperature_c": temperature_c,
        "memory_total_mb": memory_total_mb,
        "memory_used_mb": memory_used_mb,
        "memory_available_mb": memory_available_mb,
        "disk_total_gb": disk_total_gb,
        "disk_used_gb": disk_used_gb,
        "disk_free_gb": disk_free_gb,
        "hostname": hostname,
        "local_hostname": f"{hostname}.local",
        "ip_address": _ip_address(),
        "system_uptime": _system_uptime(),
        "operating_system": os_name,
        "operating_system_version": os_version,
        "architecture": platform.machine() or None,
        "server_memory_mb": minecraft_memory,
        "minecraft_memory_mb": minecraft_memory,
        **fan,
    }


def sparkline(values: list[float], width: int = 30) -> str:
    if not values:
        return "-"
    chars = " .:-=+*#%@"
    values = values[-max(1, width) :]
    return "".join(
        chars[
            min(
                len(chars) - 1,
                max(0, int(value / 100 * (len(chars) - 1))),
            )
        ]
        for value in values
    )
