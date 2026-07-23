from __future__ import annotations

from pathlib import Path
from config import BACKUP_DIR, MINECRAFT_DIR, SERVER_LOG, SERVER_PROPERTIES, SERVICE_NAME
from services import minecraft, rcon
from services.system import run


def checks() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    results.append(('Minecraft directory', MINECRAFT_DIR.is_dir(), str(MINECRAFT_DIR)))
    results.append(('server.properties', SERVER_PROPERTIES.is_file(), str(SERVER_PROPERTIES)))
    results.append(('latest.log', SERVER_LOG.is_file(), str(SERVER_LOG)))
    results.append(('mcrcon installed', Path(MCRCON_PATH).is_file(), MCRCON_PATH))
    unit = run(['systemctl', 'cat', SERVICE_NAME])
    results.append(('systemd service', unit.ok, SERVICE_NAME))
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        test = BACKUP_DIR / '.minebox-write-test'
        test.write_text('ok', encoding='utf-8'); test.unlink()
        writable = True
    except OSError:
        writable = False
    results.append(('Backup directory writable', writable, str(BACKUP_DIR)))
    if minecraft.is_running():
        ping = rcon.send('list')
        results.append(('RCON connection', ping.ok, ping.message))
    else:
        results.append(('RCON connection', True, 'Skipped while server is offline'))
    return results
