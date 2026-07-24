from __future__ import annotations

import time
from pathlib import Path
from config import MINEBOX_DATA_DIR, SERVER_LOG
from services.system import CommandResult


def read_lines(limit: int = 2000) -> list[str]:
    try:
        return SERVER_LOG.read_text(encoding='utf-8', errors='ignore').splitlines()[-limit:]
    except OSError:
        return []


def filter_lines(level: str = 'ALL', query: str = '', limit: int = 500) -> list[str]:
    lines = read_lines(max(limit * 4, 2000))
    level = level.upper()
    query_lower = query.lower().strip()
    output: list[str] = []
    for line in lines:
        upper = line.upper()
        if level != 'ALL' and f'/{level}]' not in upper and f'[{level}]' not in upper:
            continue
        if query_lower and query_lower not in line.lower():
            continue
        output.append(line.strip())
    return output[-limit:]


def export(lines: list[str], label: str = 'log-export') -> CommandResult:
    try:
        folder = MINEBOX_DATA_DIR / 'exports'
        folder.mkdir(parents=True, exist_ok=True)
        safe = ''.join(c if c.isalnum() or c in '-_' else '-' for c in label).strip('-') or 'log-export'
        target = folder / f"{safe}-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        target.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return CommandResult(True, f'Exported to {target}')
    except OSError as exc:
        return CommandResult(False, stderr=str(exc))
