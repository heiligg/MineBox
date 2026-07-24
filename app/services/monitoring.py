from __future__ import annotations

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
    values = Path('/proc/stat').read_text(encoding='utf-8').splitlines()[0].split()[1:]
    nums = [int(value) for value in values]
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    return idle, sum(nums)


def _memory_percent() -> float:
    values: dict[str, int] = {}
    for line in Path('/proc/meminfo').read_text(encoding='utf-8').splitlines():
        key, raw = line.split(':', 1)
        values[key] = int(raw.strip().split()[0])
    total = values.get('MemTotal', 1)
    available = values.get('MemAvailable', 0)
    return round((total - available) * 100 / total, 1)


def server_process_memory_mb() -> float:
    result = run(['systemctl', 'show', SERVICE_NAME, '--property=MainPID', '--value'])
    try:
        pid = int(result.stdout)
        if pid <= 0:
            return 0.0
        for line in Path(f'/proc/{pid}/status').read_text(encoding='utf-8').splitlines():
            if line.startswith('VmRSS:'):
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


def sparkline(values: list[float], width: int = 30) -> str:
    if not values:
        return '-'
    chars = ' .:-=+*#%@'
    values = values[-max(1, width):]
    return ''.join(chars[min(len(chars) - 1, max(0, int(value / 100 * (len(chars) - 1))))] for value in values)


def _cpu_temperature_c() -> float | None:
    for path in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
        try:
            value = float(path.read_text(encoding='utf-8').strip())
            if value > 1000:
                value /= 1000
            if -20 <= value <= 150:
                return round(value, 1)
        except (OSError, ValueError):
            continue
    return None


def _os_release() -> dict[str, str]:
    values = {}
    try:
        for line in Path('/etc/os-release').read_text(encoding='utf-8').splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                values[key] = value.strip().strip('"')
    except OSError:
        pass
    return values


def _system_uptime() -> str:
    try:
        seconds = int(float(Path('/proc/uptime').read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        return 'Unavailable'
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    if days:
        return f'{days}d {hours}h {minutes}m'
    if hours:
        return f'{hours}h {minutes}m'
    return f'{minutes}m'


def _primary_ip() -> str:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('8.8.8.8', 80))
            return sock.getsockname()[0]
    except OSError:
        return 'Unavailable'


def system_status() -> dict:
    import os
    import platform
    import shutil
    import socket

    current = sample()

    memory_values = {}
    try:
        for line in Path('/proc/meminfo').read_text(encoding='utf-8').splitlines():
            key, raw = line.split(':', 1)
            memory_values[key] = int(raw.strip().split()[0]) / 1024
    except (OSError, ValueError, IndexError):
        pass

    memory_total = round(memory_values.get('MemTotal', 0), 1)
    memory_available = round(memory_values.get('MemAvailable', 0), 1)
    memory_used = round(max(0, memory_total - memory_available), 1)

    try:
        disk = shutil.disk_usage('/')
        disk_total = round(disk.total / (1024 ** 3), 1)
        disk_used = round(disk.used / (1024 ** 3), 1)
        disk_free = round(disk.free / (1024 ** 3), 1)
        disk_percent = round((disk.used / disk.total) * 100, 1) if disk.total else 0.0
    except OSError:
        disk_total = disk_used = disk_free = disk_percent = 0.0

    release = _os_release()
    hostname = socket.gethostname()

    return {
        'cpu_percent': current.cpu,
        'cpu_temperature_c': _cpu_temperature_c(),
        'memory_percent': current.memory,
        'memory_total_mb': memory_total,
        'memory_used_mb': memory_used,
        'memory_available_mb': memory_available,
        'disk_percent': disk_percent,
        'disk_total_gb': disk_total,
        'disk_used_gb': disk_used,
        'disk_free_gb': disk_free,
        'hostname': hostname,
        'local_hostname': f'{hostname}.local',
        'ip_address': _primary_ip(),
        'system_uptime': _system_uptime(),
        'operating_system': release.get('NAME') or platform.system(),
        'operating_system_version': release.get('VERSION_ID') or platform.release(),
        'architecture': platform.machine(),
        'minecraft_memory_mb': current.server_memory_mb,
        'load_average': list(os.getloadavg()) if hasattr(os, 'getloadavg') else [],
    }
