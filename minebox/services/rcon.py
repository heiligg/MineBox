from __future__ import annotations
import re
from config import MCRCON_PATH, RCON_HOST, RCON_PORT, RCON_PASSWORD
from services.system import CommandResult, run

def send(command: str) -> CommandResult:
    return run([MCRCON_PATH, "-H", RCON_HOST, "-P", RCON_PORT, "-p", RCON_PASSWORD, command], timeout=15)

def players() -> tuple[list[str], int] | None:
    result = send("list")
    if not result.ok:
        return None
    match = re.search(r"There are (\d+) of a max of (\d+) players online:?(.*)", result.stdout, re.I)
    if not match:
        return None
    names = [name.strip() for name in match.group(3).split(",") if name.strip()]
    return names, int(match.group(2))
