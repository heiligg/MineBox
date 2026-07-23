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
