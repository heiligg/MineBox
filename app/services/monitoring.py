from __future__ import annotations

import platform
import shutil
import socket
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    values = (
        Path("/proc/stat")
        .read_text(encoding="utf-8")
        .splitlines()[0]
        .split()[1:]
    )

    numbers = [int(value) for value in values]
    idle = numbers[3] + (numbers[4] if len(numbers) > 4 else 0)

    return idle, sum(numbers)


def _memory_values_kb() -> dict[str, int]:
    values: dict[str, int] = {}

    for line in Path("/proc/meminfo").read_text(
        encoding="utf-8"
    ).splitlines():
        key, raw_value = line.split(":", 1)
        values[key] = int(raw_value.strip().split()[0])

    return values


def _memory_details() -> dict[str, float]:
    values = _memory_values_kb()

    total_kb = values.get("MemTotal", 1)
    available_kb = values.get("MemAvailable", 0)
    used_kb = max(0, total_kb - available_kb)

    return {
        "used_mb": round(used_kb / 1024, 1),
        "total_mb": round(total_kb / 1024, 1),
        "available_mb": round(available_kb / 1024, 1),
        "percent": round(used_kb * 100 / total_kb, 1),
    }


def _cpu_temperature_c() -> float | None:
    temperature_files = sorted(
        Path("/sys/class/thermal").glob("thermal_zone*/temp")
    )

    for temperature_file in temperature_files:
        try:
            raw_value = float(
                temperature_file.read_text(encoding="utf-8").strip()
            )

            temperature = (
                raw_value / 1000 if raw_value > 200 else raw_value
            )

            if 0 < temperature < 150:
                return round(temperature, 1)
        except (OSError, ValueError):
            continue

    return None


def _disk_details() -> dict[str, float]:
    usage = shutil.disk_usage("/")

    gibibyte = 1024 ** 3
    percent = (
        round(usage.used * 100 / usage.total, 1)
        if usage.total
        else 0.0
    )

    return {
        "used_gb": round(usage.used / gibibyte, 1),
        "total_gb": round(usage.total / gibibyte, 1),
        "free_gb": round(usage.free / gibibyte, 1),
        "percent": percent,
    }


def _format_duration(total_seconds: float) -> str:
    seconds = max(0, int(total_seconds))

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)

    parts: list[str] = []

    if days:
        parts.append(f"{days}d")

    if hours or days:
        parts.append(f"{hours}h")

    parts.append(f"{minutes}m")

    return " ".join(parts)


def _system_uptime() -> dict[str, Any]:
    try:
        seconds = float(
            Path("/proc/uptime")
            .read_text(encoding="utf-8")
            .split()[0]
        )
    except (OSError, ValueError, IndexError):
        seconds = 0.0

    return {
        "seconds": int(seconds),
        "text": _format_duration(seconds),
    }


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "minebox"


def _local_ip_address() -> str:
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        connection.connect(("1.1.1.1", 80))
        address = connection.getsockname()[0]

        if address:
            return address
    except OSError:
        pass
    finally:
        connection.close()

    try:
        return socket.gethostbyname(_hostname())
    except OSError:
        return "Unavailable"


def server_process_memory_mb() -> float:
    result = run(
        [
            "systemctl",
            "show",
            SERVICE_NAME,
            "--property=MainPID",
            "--value",
        ]
    )

    try:
        pid = int(result.stdout)

        if pid <= 0:
            return 0.0

        status_file = Path(f"/proc/{pid}/status")

        for line in status_file.read_text(
            encoding="utf-8"
        ).splitlines():
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

        cpu = round(
            100 * (1 - (idle2 - idle1) / delta),
            1,
        )
    except (OSError, ValueError, IndexError):
        cpu = 0.0

    try:
        memory = _memory_details()["percent"]
    except (OSError, ValueError, IndexError):
        memory = 0.0

    item = Sample(
        timestamp=time.time(),
        cpu=cpu,
        memory=memory,
        server_memory_mb=server_process_memory_mb(),
    )

    _HISTORY.append(item)

    return item


def system_status() -> dict[str, Any]:
    current_sample = sample()

    try:
        memory = _memory_details()
    except (OSError, ValueError, IndexError):
        memory = {
            "used_mb": 0.0,
            "total_mb": 0.0,
            "available_mb": 0.0,
            "percent": current_sample.memory,
        }

    try:
        disk = _disk_details()
    except OSError:
        disk = {
            "used_gb": 0.0,
            "total_gb": 0.0,
            "free_gb": 0.0,
            "percent": 0.0,
        }

    hostname = _hostname()
    uptime = _system_uptime()

    return {
        "cpu_percent": current_sample.cpu,
        "cpu_temperature_c": _cpu_temperature_c(),
        "memory_percent": memory["percent"],
        "memory_used_mb": memory["used_mb"],
        "memory_total_mb": memory["total_mb"],
        "memory_available_mb": memory["available_mb"],
        "disk_percent": disk["percent"],
        "disk_used_gb": disk["used_gb"],
        "disk_total_gb": disk["total_gb"],
        "disk_free_gb": disk["free_gb"],
        "minecraft_memory_mb": current_sample.server_memory_mb,
        "hostname": hostname,
        "local_hostname": f"{hostname}.local",
        "ip_address": _local_ip_address(),
        "system_uptime_seconds": uptime["seconds"],
        "system_uptime": uptime["text"],
        "operating_system": platform.system(),
        "operating_system_version": platform.release(),
        "architecture": platform.machine(),
    }


def history() -> list[Sample]:
    return list(_HISTORY)


def sparkline(values: list[float], width: int = 30) -> str:
    if not values:
        return "-"

    characters = " .:-=+*#%@"
    values = values[-max(1, width):]

    return "".join(
        characters[
            min(
                len(characters) - 1,
                max(
                    0,
                    int(
                        value
                        / 100
                        * (len(characters) - 1)
                    ),
                ),
            )
        ]
        for value in values
    )
