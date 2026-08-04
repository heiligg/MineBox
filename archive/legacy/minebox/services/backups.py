from __future__ import annotations
import shutil
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from config import BACKUP_DIR, MINECRAFT_DIR
from services.system import CommandResult
from services import minecraft, settings

@dataclass
class Backup:
    path: Path
    size: int
    modified: float

    @property
    def label(self) -> str:
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.modified))
        return f"{stamp}  {self.size / (1024*1024):.1f} MB"

def list_backups() -> list[Backup]:
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        return sorted([Backup(p, p.stat().st_size, p.stat().st_mtime) for p in BACKUP_DIR.glob("minebox-*.tar.gz")], key=lambda x: x.modified, reverse=True)
    except OSError:
        return []

def prune() -> CommandResult:
    keep = max(1, int(settings.load().get("backup_retention", 10)))
    removed = 0
    for backup in list_backups()[keep:]:
        try: backup.path.unlink(); removed += 1
        except OSError as exc: return CommandResult(False, stderr=str(exc))
    return CommandResult(True, f"Removed {removed} old backup(s).")

def create() -> CommandResult:
    save = minecraft.save_world()
    if not save.ok: return save
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        name = time.strftime("minebox-%Y%m%d-%H%M%S.tar.gz")
        target = BACKUP_DIR / name
        with tarfile.open(target, "w:gz") as archive:
            for child in MINECRAFT_DIR.iterdir():
                if child.resolve() != BACKUP_DIR.resolve(): archive.add(child, arcname=child.name)
        prune_result = prune()
        suffix = "" if prune_result.ok else f" Warning: {prune_result.message}"
        return CommandResult(True, f"Backup created: {name}.{suffix}")
    except (OSError, tarfile.TarError) as exc:
        return CommandResult(False, stderr=str(exc))

def delete(backup: Backup) -> CommandResult:
    try: backup.path.unlink(); return CommandResult(True, "Backup deleted.")
    except OSError as exc: return CommandResult(False, stderr=str(exc))

def restore(backup: Backup) -> CommandResult:
    was_running = minecraft.is_running()
    if was_running:
        stopped = minecraft.stop()
        if not stopped.ok: return stopped
    try:
        with tarfile.open(backup.path, "r:gz") as archive:
            for member in archive.getmembers():
                target = (MINECRAFT_DIR / member.name).resolve()
                if not str(target).startswith(str(MINECRAFT_DIR.resolve())):
                    return CommandResult(False, stderr="Unsafe path found inside backup.")
        for child in MINECRAFT_DIR.iterdir():
            if child.resolve() == BACKUP_DIR.resolve(): continue
            if child.is_dir(): shutil.rmtree(child)
            else: child.unlink()
        with tarfile.open(backup.path, "r:gz") as archive:
            archive.extractall(MINECRAFT_DIR, filter="data")
    except (OSError, tarfile.TarError) as exc:
        return CommandResult(False, stderr=str(exc))
    if was_running:
        started = minecraft.start()
        if not started.ok: return CommandResult(False, stderr=f"Backup restored, but Minecraft could not restart: {started.message}")
    return CommandResult(True, "Backup restored successfully.")
