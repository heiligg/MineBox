from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services import minecraft
from services import servers
from services.system import CommandResult


def _minecraft_dir() -> Path:
    return servers.MINECRAFT_ROOT


def _shared_backup_dir() -> Path:
    return _minecraft_dir() / "backups"


def _server_backup_key(server_id: str | None = None) -> str:
    raw = (server_id or "").strip()
    if not raw:
        active = servers.active_server()
        raw = active.server_id if active is not None else "default"
    key = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw)[:32]
    return key or "default"


def _backup_dir() -> Path:
    return _shared_backup_dir() / _server_backup_key()


def _migrate_legacy_backups(dest: Path) -> None:
    """Move this server's old shared-root archives into its private folder."""
    try:
        dest_resolved = dest.resolve()
        shared = _shared_backup_dir().resolve()
    except OSError:
        return
    if not shared.is_dir() or dest_resolved == shared:
        return
    prefix = f"{BACKUP_PREFIX}{dest_resolved.name}-"
    try:
        dest_resolved.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    try:
        children = list(shared.iterdir())
    except OSError:
        return
    for path in children:
        if not path.is_file():
            continue
        if not (path.name.startswith(prefix) and path.name.endswith(BACKUP_SUFFIX)):
            continue
        target = dest_resolved / path.name
        try:
            if not target.exists():
                path.replace(target)
            sidecar = Path(str(path) + ".sha256")
            if sidecar.is_file():
                side_target = dest_resolved / sidecar.name
                if not side_target.exists():
                    sidecar.replace(side_target)
                else:
                    sidecar.unlink(missing_ok=True)
        except OSError:
            continue


def _world_dir() -> Path:
    active = servers.active_server()
    if active is not None:
        return Path(active.directory) / "world"
    return _minecraft_dir() / "world"


# Compatibility aliases for the SPI menu and maintenance runner.
MINECRAFT_DIR = servers.MINECRAFT_ROOT
BACKUP_DIR = servers.MINECRAFT_ROOT / "backups"
WORLD_DIR = servers.MINECRAFT_ROOT / "world"

BACKUP_PREFIX = "world-"
BACKUP_SUFFIX = ".tar.gz"

DEFAULT_RETENTION = 10

_backup_lock = threading.Lock()


@dataclass
class BackupError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass
class Backup:
    """Legacy backup record used by the local SPI menu."""

    path: Path
    size: int
    modified: float

    @property
    def label(self) -> str:
        stamp = time_strftime(self.modified)
        return f"{stamp}  {self.size / (1024 * 1024):.1f} MB"


def time_strftime(modified: float) -> str:
    return datetime.fromtimestamp(modified).strftime("%Y-%m-%d %H:%M")


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"

            return f"{size:.1f} {unit}"

        size /= 1024

    return f"{size_bytes} B"


def _backup_info(path: Path) -> dict[str, Any]:
    stat = path.stat()

    created = datetime.fromtimestamp(
        stat.st_mtime,
        tz=timezone.utc,
    )

    return {
        "filename": path.name,
        "size_bytes": stat.st_size,
        "size": _format_size(stat.st_size),
        "created_at": created.isoformat(),
        "created_timestamp": stat.st_mtime,
    }


def _backup_files() -> list[Path]:
    backup_directory = _backup_dir()
    _migrate_legacy_backups(backup_directory)
    if not backup_directory.exists():
        return []

    backups = [
        path
        for path in backup_directory.iterdir()
        if (
            path.is_file()
            and path.name.startswith(BACKUP_PREFIX)
            and path.name.endswith(BACKUP_SUFFIX)
        )
    ]

    return sorted(
        backups,
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def list_backups() -> list[dict[str, Any]]:
    return [
        _backup_info(path)
        for path in _backup_files()
    ]


def backup_status() -> dict[str, Any]:
    from services import maintenance
    from services import settings as minebox_settings

    backups = list_backups()
    cfg = minebox_settings.load()
    retention = int(cfg.get("backup_retention", DEFAULT_RETENTION) or DEFAULT_RETENTION)
    interval_hours = max(0, int(cfg.get("automatic_backup_hours", 0) or 0))
    state = maintenance._state()
    last_auto = float(state.get("last_auto_backup", 0) or 0)
    next_due = None
    if interval_hours > 0:
        next_due = last_auto + (interval_hours * 3600) if last_auto else None
    active = servers.active_server()

    return {
        "backup_directory": str(_backup_dir()),
        "world_directory": str(_world_dir()),
        "server_id": active.server_id if active is not None else None,
        "server_name": active.name if active is not None else None,
        "backup_count": len(backups),
        "busy": _backup_lock.locked(),
        "retention": retention,
        "automatic_backup_hours": interval_hours,
        "last_auto_backup": last_auto or None,
        "next_auto_backup": next_due,
        "backups": backups,
    }


def update_backup_settings(
    *,
    automatic_backup_hours: int | None = None,
    retention: int | None = None,
) -> dict[str, Any]:
    from services import settings as minebox_settings

    cfg = minebox_settings.load()
    if automatic_backup_hours is not None:
        hours = int(automatic_backup_hours)
        if hours < 0 or hours > 168:
            raise BackupError("Automatic backup hours must be between 0 and 168.")
        cfg["automatic_backup_hours"] = hours
    if retention is not None:
        keep = int(retention)
        if keep < 1 or keep > 100:
            raise BackupError("Retention must be between 1 and 100.")
        cfg["backup_retention"] = keep
    ok, message = minebox_settings.save(cfg)
    if not ok:
        raise BackupError(message or "Could not save backup settings.")
    return backup_status()


def _preserve_last_backup() -> bool:
    try:
        from core.minebox_config import get_config

        return bool(get_config().preserve_last_backup)
    except Exception:
        return True


def _remove_old_backups(retention: int) -> list[str]:
    retention = max(1, retention)
    backups = _backup_files()
    removed: list[str] = []

    # Never silently delete the only valid backup when configured.
    if _preserve_last_backup() and len(backups) <= 1:
        return removed

    for path in backups[retention:]:
        if _preserve_last_backup() and len(backups) - len(removed) <= 1:
            break
        try:
            path.unlink()
            removed.append(path.name)
            # Drop sidecar checksum if present.
            side = Path(str(path) + ".sha256")
            if side.is_file():
                side.unlink(missing_ok=True)
        except OSError:
            continue

    return removed


def _disk_free_bytes(path: Path) -> int | None:
    try:
        usage = shutil.disk_usage(path)
        return int(usage.free)
    except OSError:
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checksum(path: Path) -> str:
    checksum = _sha256_file(path)
    side = Path(str(path) + ".sha256")
    side.write_text(f"{checksum}  {path.name}\n", encoding="utf-8")
    return checksum


def _rcon_save_command(command: str) -> None:
    from services import rcon

    result = rcon.send(command)
    if not result.ok:
        raise BackupError(f"RCON {command} failed: {result.message}")


def _set_autosave(enabled: bool) -> None:
    _rcon_save_command("save-on" if enabled else "save-off")




# MineBox Backup Management v2

def get_backup_path(filename: str) -> Path:
    """
    Return a validated path for an existing MineBox backup.

    Only normal filenames generated by MineBox are accepted.
    Directory traversal and files outside BACKUP_DIR are rejected.
    """

    if not isinstance(filename, str) or not filename:
        raise BackupError("A backup filename is required.")

    if filename != Path(filename).name:
        raise BackupError("Invalid backup filename.")

    if (
        not filename.startswith(BACKUP_PREFIX)
        or not filename.endswith(BACKUP_SUFFIX)
    ):
        raise BackupError("Invalid backup filename.")

    try:
        backup_directory = _backup_dir().resolve()
        backup_path = (_backup_dir() / filename).resolve()
    except OSError as exc:
        raise BackupError(
            f"Could not resolve the backup path: {exc}"
        ) from exc

    if backup_path.parent != backup_directory:
        raise BackupError("Invalid backup filename.")

    if not backup_path.is_file():
        raise BackupError(
            f"Backup {filename} does not exist."
        )

    return backup_path


def delete_backup(filename: str) -> dict[str, Any]:
    if not _backup_lock.acquire(blocking=False):
        raise BackupError(
            "Another backup operation is already running."
        )

    try:
        backup_path = get_backup_path(filename)
        backup_info = _backup_info(backup_path)
        if _preserve_last_backup() and len(_backup_files()) <= 1:
            raise BackupError(
                "Refusing to delete the only remaining backup "
                "(preserve_last_backup is enabled)."
            )

        try:
            backup_path.unlink()
            Path(str(backup_path) + ".sha256").unlink(missing_ok=True)
        except OSError as exc:
            raise BackupError(
                f"Could not delete backup {filename}: {exc}"
            ) from exc

        return {
            **backup_info,
            "message": (
                f"Backup {filename} was deleted successfully."
            ),
        }

    finally:
        _backup_lock.release()




# MineBox Safe Restore Engine v3

def _command_error(result: Any, fallback: str) -> str:
    return (
        getattr(result, "stderr", "")
        or getattr(result, "stdout", "")
        or fallback
    )


def _unique_backup_path(prefix: str) -> Path:
    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    filename = f"{prefix}{timestamp}{BACKUP_SUFFIX}"
    path = _backup_dir() / filename
    counter = 1

    while path.exists():
        filename = (
            f"{prefix}{timestamp}-{counter}"
            f"{BACKUP_SUFFIX}"
        )
        path = _backup_dir() / filename
        counter += 1

    return path


def _create_world_archive(
    final_path: Path,
) -> dict[str, Any]:
    world_directory = _world_dir()
    if not world_directory.is_dir():
        raise BackupError(
            f"Minecraft world directory does not exist: "
            f"{world_directory}"
        )

    _backup_dir().mkdir(
        parents=True,
        exist_ok=True,
    )

    partial_path = (
        _backup_dir()
        / f".{final_path.name}.partial"
    )

    try:
        with tarfile.open(
            partial_path,
            mode="w:gz",
            compresslevel=6,
        ) as archive:
            archive.add(
                world_directory,
                arcname="world",
                recursive=True,
            )

        os.replace(
            partial_path,
            final_path,
        )

    except (OSError, tarfile.TarError) as exc:
        raise BackupError(
            f"Could not create safety backup: {exc}"
        ) from exc

    finally:
        if partial_path.exists():
            try:
                partial_path.unlink()
            except OSError:
                pass

    return _backup_info(final_path)


def _validate_archive_member(
    member: tarfile.TarInfo,
) -> None:
    member_path = Path(member.name)

    if member_path.is_absolute():
        raise BackupError(
            "Backup archive contains an absolute path."
        )

    if ".." in member_path.parts:
        raise BackupError(
            "Backup archive contains an unsafe path."
        )

    if not member_path.parts:
        raise BackupError(
            "Backup archive contains an invalid entry."
        )

    # Allow MineBox metadata at archive root; everything else must be under world/.
    if member_path.parts[0] == "minebox-manifest.json" and len(member_path.parts) == 1:
        return

    if member_path.parts[0] != "world":
        raise BackupError(
            "Backup archive must contain only a "
            "top-level world directory (plus optional minebox-manifest.json)."
        )

    if (
        member.issym()
        or member.islnk()
        or member.ischr()
        or member.isblk()
        or member.isfifo()
    ):
        raise BackupError(
            "Backup archive contains an unsupported "
            "link or special file."
        )

    if not (
        member.isdir()
        or member.isfile()
    ):
        raise BackupError(
            "Backup archive contains an unsupported "
            "entry type."
        )


def validate_backup_archive(
    filename: str,
) -> dict[str, Any]:
    backup_path = get_backup_path(filename)

    found_level_dat = False
    found_region = False
    member_count = 0

    try:
        with tarfile.open(
            backup_path,
            mode="r:gz",
        ) as archive:
            members = archive.getmembers()

            if not members:
                raise BackupError(
                    "Backup archive is empty."
                )

            for member in members:
                _validate_archive_member(member)
                member_count += 1

                normalized = member.name.rstrip("/")

                if normalized == "world/level.dat":
                    found_level_dat = member.isfile()

                if normalized == "world/region":
                    found_region = member.isdir()

    except BackupError:
        raise

    except (OSError, tarfile.TarError) as exc:
        raise BackupError(
            f"Backup archive could not be read: {exc}"
        ) from exc

    if not found_level_dat:
        raise BackupError(
            "Backup archive does not contain "
            "world/level.dat."
        )

    if not found_region:
        raise BackupError(
            "Backup archive does not contain "
            "the world/region directory."
        )

    return {
        "filename": backup_path.name,
        "member_count": member_count,
        "has_level_dat": True,
        "has_region": True,
        "message": (
            f"Backup {backup_path.name} passed "
            f"archive validation."
        ),
    }


def _extract_backup_to_staging(
    backup_path: Path,
    staging_directory: Path,
) -> Path:
    try:
        staging_directory.mkdir(
            parents=True,
            exist_ok=False,
        )

        with tarfile.open(
            backup_path,
            mode="r:gz",
        ) as archive:
            members = archive.getmembers()

            for member in members:
                _validate_archive_member(member)

            archive.extractall(
                path=staging_directory,
                members=members,
            )

    except BackupError:
        raise

    except (OSError, tarfile.TarError) as exc:
        raise BackupError(
            f"Could not extract backup archive: {exc}"
        ) from exc

    staged_world = staging_directory / "world"

    if not staged_world.is_dir():
        raise BackupError(
            "Extracted backup does not contain "
            "a world directory."
        )

    if not (staged_world / "level.dat").is_file():
        raise BackupError(
            "Extracted world is missing level.dat."
        )

    if not (staged_world / "region").is_dir():
        raise BackupError(
            "Extracted world is missing its "
            "region directory."
        )

    return staged_world


def _remove_path(path: Path) -> None:
    if not path.exists():
        return

    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def restore_backup(
    filename: str,
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    if not confirm:
        raise BackupError(
            "Restore requires explicit confirm=true at the service/API layer."
        )

    from services.operations import OperationConflict, OperationType, get_coordinator

    coordinator = get_coordinator()
    try:
        op = coordinator.begin(OperationType.RESTORE, step="validate")
    except OperationConflict as exc:
        raise BackupError(str(exc)) from exc

    if not _backup_lock.acquire(blocking=False):
        coordinator.complete(op.id, error="busy")
        raise BackupError(
            "Another backup operation is already running."
        )

    operation_id = uuid.uuid4().hex[:12]

    staging_directory = (
        _minecraft_dir()
        / f".minebox-restore-staging-{operation_id}"
    )

    rollback_world = (
        _minecraft_dir()
        / f".minebox-world-rollback-{operation_id}"
    )

    backup_path: Path | None = None
    staged_world: Path | None = None
    safety_backup: dict[str, Any] | None = None

    was_running = False
    live_world_moved = False
    restored_world_installed = False

    try:
        coordinator.update(op.id, progress=0.1, step="validate_archive")
        backup_path = get_backup_path(filename)

        validation = validate_backup_archive(filename)
        # Optional checksum sidecar verification.
        side = Path(str(backup_path) + ".sha256")
        if side.is_file():
            expected = side.read_text(encoding="utf-8").split()[0].strip()
            actual = _sha256_file(backup_path)
            if expected != actual:
                raise BackupError("Backup checksum mismatch.")

        coordinator.update(op.id, progress=0.25, step="extract_staging")
        staged_world = _extract_backup_to_staging(
            backup_path,
            staging_directory,
        )

        was_running = minecraft.is_running()

        if was_running:
            coordinator.update(op.id, progress=0.35, step="stop_server")
            stop_result = minecraft.stop_service()

            if not stop_result.ok:
                raise BackupError(
                    "Could not stop Minecraft before restore: "
                    + _command_error(
                        stop_result,
                        "Unknown service stop error.",
                    )
                )

        safety_path = _unique_backup_path(
            "world-before-restore-"
        )

        safety_backup = _create_world_archive(
            safety_path
        )

        if rollback_world.exists():
            _remove_path(rollback_world)

        try:
            _world_dir().rename(rollback_world)
            live_world_moved = True

            staged_world.rename(_world_dir())
            restored_world_installed = True

        except OSError as exc:
            raise BackupError(
                f"Could not install restored world: {exc}"
            ) from exc

        if not (_world_dir() / "level.dat").is_file():
            raise BackupError(
                "Restored world failed verification: "
                "level.dat is missing."
            )

        if not (_world_dir() / "region").is_dir():
            raise BackupError(
                "Restored world failed verification: "
                "region directory is missing."
            )

        if was_running:
            coordinator.update(op.id, progress=0.85, step="start_server")
            start_result = minecraft.start_service()

            if not start_result.ok:
                raise BackupError(
                    "Minecraft did not start with the "
                    "restored world: "
                    + _command_error(
                        start_result,
                        "Unknown service start error.",
                    )
                )

        if rollback_world.exists():
            _remove_path(rollback_world)

        result = {
            "filename": backup_path.name,
            "message": (
                f"Backup {backup_path.name} was restored "
                f"successfully."
            ),
            "server_was_running": was_running,
            "server_running": minecraft.is_running(),
            "archive_validation": validation,
            "safety_backup": safety_backup,
            "rolled_back": False,
            "operation_id": op.id,
        }
        coordinator.complete(op.id)
        return result

    except Exception as original_error:
        rollback_errors: list[str] = []

        if live_world_moved:
            if minecraft.is_running():
                stop_result = minecraft.stop_service()

                if not stop_result.ok:
                    rollback_errors.append(
                        "Could not stop Minecraft during "
                        "rollback: "
                        + _command_error(
                            stop_result,
                            "Unknown stop error.",
                        )
                    )

            try:
                if restored_world_installed and _world_dir().exists():
                    _remove_path(_world_dir())

                if rollback_world.exists():
                    rollback_world.rename(_world_dir())

            except OSError as exc:
                rollback_errors.append(
                    f"Could not restore the original world: {exc}"
                )

            if (
                was_running
                and _world_dir().exists()
                and not minecraft.is_running()
            ):
                restart_result = minecraft.start_service()

                if not restart_result.ok:
                    rollback_errors.append(
                        "Could not restart Minecraft after "
                        "rollback: "
                        + _command_error(
                            restart_result,
                            "Unknown restart error.",
                        )
                    )

        if isinstance(original_error, BackupError):
            message = str(original_error)
        else:
            message = (
                "Unexpected restore failure: "
                f"{original_error}"
            )

        if rollback_errors:
            message += (
                " Automatic rollback also reported: "
                + " | ".join(rollback_errors)
            )

        elif live_world_moved:
            message += (
                " The original world was restored "
                "automatically."
            )

        coordinator.complete(op.id, error=message)
        raise BackupError(message) from original_error

    finally:
        # MineBox Restore Rollback Cleanup Fix v3
        #
        # The extraction staging directory is always temporary.
        # The rollback world is intentionally NOT deleted here.
        # If rollback itself fails, preserving that directory may
        # be the only remaining copy of the original live world.
        if staging_directory.exists():
            try:
                _remove_path(staging_directory)
            except OSError:
                pass

        _backup_lock.release()


def create_backup(
    retention: int = DEFAULT_RETENTION,
) -> dict[str, Any]:
    from services.operations import OperationConflict, OperationType, get_coordinator
    from services import minecraft_health

    coordinator = get_coordinator()
    try:
        op = coordinator.begin(OperationType.BACKUP, step="prepare")
    except OperationConflict as exc:
        raise BackupError(str(exc)) from exc

    if not _backup_lock.acquire(blocking=False):
        coordinator.complete(op.id, error="busy")
        raise BackupError("Another backup is already running.")

    partial_path: Path | None = None
    autosave_disabled = False
    was_running = False
    lifecycle = None

    try:
        from services.lifecycle import get_lifecycle

        lifecycle = get_lifecycle()
        world_directory = _world_dir()
        if not world_directory.is_dir():
            raise BackupError(
                f"Minecraft world directory does not exist: {world_directory}"
            )

        try:
            _backup_dir().mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise BackupError(f"Could not create the backup directory: {exc}") from exc

        # Storage precheck — require roughly 2x world size free when measurable.
        free = _disk_free_bytes(_backup_dir())
        try:
            world_size = sum(
                p.stat().st_size for p in world_directory.rglob("*") if p.is_file()
            )
        except OSError:
            world_size = 0
        if free is not None and world_size > 0 and free < (world_size * 2):
            raise BackupError(
                "Not enough free disk space for a safe backup "
                f"(free={free}, world≈{world_size})."
            )

        was_running = minecraft.is_running()
        try:
            lifecycle.begin_backup_state()
        except Exception as exc:  # noqa: BLE001
            raise BackupError(str(exc)) from exc

        save_message = "Server offline; archived without live save."
        if was_running:
            coordinator.update(op.id, progress=0.15, step="health_check")
            health = minecraft_health.collect_health()
            if not health.healthy and health.phase != "starting":
                # Allow backup of a wedged server after best-effort save, but note it.
                save_message = "Server unhealthy; attempting best-effort save."
            coordinator.update(op.id, progress=0.25, step="save_flush")
            save_result = minecraft.save_world()
            if not save_result.ok:
                raise BackupError(
                    f"World save failed: {save_result.stderr or save_result.stdout or 'unknown'}"
                )
            save_message = save_result.stdout or "World save completed."
            try:
                coordinator.update(op.id, progress=0.35, step="save_off")
                _set_autosave(False)
                autosave_disabled = True
                time.sleep(1.0)
            except BackupError:
                # Older servers may not support save-off; continue carefully.
                autosave_disabled = False
                save_message += " (save-off unsupported)"

        active = servers.active_server()
        server_id = active.server_id if active else "default"
        version = ""
        try:
            version = minecraft.version() or ""
        except Exception:
            version = ""

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_id = _server_backup_key(server_id)
        filename = f"{BACKUP_PREFIX}{safe_id}-{timestamp}{BACKUP_SUFFIX}"

        final_path = _backup_dir() / filename
        partial_path = _backup_dir() / f".{filename}.partial"
        counter = 1
        while final_path.exists() or partial_path.exists():
            filename = f"{BACKUP_PREFIX}{safe_id}-{timestamp}-{counter}{BACKUP_SUFFIX}"
            final_path = _backup_dir() / filename
            partial_path = _backup_dir() / f".{filename}.partial"
            counter += 1

        coordinator.update(op.id, progress=0.55, step="archive")
        manifest = {
            "minebox_backup_version": 1,
            "server_id": server_id,
            "minecraft_version": version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "was_running": was_running,
        }
        manifest_path = _backup_dir() / f".manifest-{uuid.uuid4().hex}.json"
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            with tarfile.open(partial_path, mode="w:gz", compresslevel=6) as archive:
                archive.add(world_directory, arcname="world", recursive=True)
                archive.add(manifest_path, arcname="minebox-manifest.json")
            os.replace(partial_path, final_path)
        except (OSError, tarfile.TarError) as exc:
            raise BackupError(f"Could not create the backup archive: {exc}") from exc
        finally:
            if manifest_path.exists():
                try:
                    manifest_path.unlink()
                except OSError:
                    pass

        coordinator.update(op.id, progress=0.8, step="verify")
        # Validate members (world/…). Manifest is extra and allowed.
        try:
            with tarfile.open(final_path, mode="r:gz") as archive:
                members = archive.getmembers()
                if not members:
                    raise BackupError("Backup archive is empty.")
                found_level = False
                found_region = False
                for member in members:
                    # Allow manifest at archive root.
                    if member.name.rstrip("/") == "minebox-manifest.json":
                        continue
                    _validate_archive_member(member)
                    normalized = member.name.rstrip("/")
                    if normalized == "world/level.dat" and member.isfile():
                        found_level = True
                    if normalized == "world/region" and member.isdir():
                        found_region = True
                if not found_level or not found_region:
                    raise BackupError("Backup archive failed post-create validation.")
        except BackupError:
            try:
                final_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        except (OSError, tarfile.TarError) as exc:
            try:
                final_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise BackupError(f"Backup verification failed: {exc}") from exc

        checksum = _write_checksum(final_path)
        removed = _remove_old_backups(retention)
        result = _backup_info(final_path)
        result.update(
            {
                "message": f"Backup {final_path.name} was created successfully.",
                "world_saved": True,
                "save_message": save_message,
                "removed_backups": removed,
                "checksum_sha256": checksum,
                "manifest": manifest,
                "server_id": server_id,
                "operation_id": op.id,
            }
        )
        if lifecycle is not None:
            lifecycle.end_backup_state(was_running=was_running)
        coordinator.complete(op.id)
        return result

    except Exception as exc:
        if lifecycle is not None:
            try:
                lifecycle.end_backup_state(
                    was_running=was_running,
                    error=str(exc),
                )
            except Exception:
                pass
        coordinator.complete(op.id, error=str(exc))
        if isinstance(exc, BackupError):
            raise
        raise BackupError(str(exc)) from exc

    finally:
        if autosave_disabled:
            try:
                _set_autosave(True)
            except Exception:
                # Never leave autosave disabled if we can help it.
                try:
                    from services import rcon

                    rcon.send("save-on")
                except Exception:
                    pass
        if partial_path is not None and partial_path.exists():
            try:
                partial_path.unlink()
            except OSError:
                pass
        _backup_lock.release()


def create() -> CommandResult:
    """SPI menu / maintenance compatibility wrapper."""
    try:
        result = create_backup()
        return CommandResult(
            True,
            result.get("message", "Backup created."),
        )
    except BackupError as error:
        return CommandResult(False, stderr=str(error))


def prune() -> CommandResult:
    removed = _remove_old_backups(DEFAULT_RETENTION)
    return CommandResult(
        True,
        f"Removed {len(removed)} old backup(s).",
    )


def legacy_list_backups() -> list[Backup]:
    return [
        Backup(
            path=path,
            size=path.stat().st_size,
            modified=path.stat().st_mtime,
        )
        for path in _backup_files()
    ]


def delete(backup: Backup) -> CommandResult:
    try:
        delete_backup(backup.path.name)
        return CommandResult(True, "Backup deleted.")
    except BackupError as error:
        return CommandResult(False, stderr=str(error))


def restore(backup: Backup) -> CommandResult:
    try:
        restore_backup(backup.path.name, confirm=True)
        return CommandResult(True, "Backup restored successfully.")
    except BackupError as error:
        return CommandResult(False, stderr=str(error))
