from __future__ import annotations

import os
import shutil
import tarfile
import threading
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


def _backup_dir() -> Path:
    return _minecraft_dir() / "backups"


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

    return {
        "backup_directory": str(_backup_dir()),
        "world_directory": str(_world_dir()),
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


def _remove_old_backups(retention: int) -> list[str]:
    retention = max(1, retention)
    backups = _backup_files()
    removed: list[str] = []

    for path in backups[retention:]:
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            continue

    return removed




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

        try:
            backup_path.unlink()
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

    if member_path.parts[0] != "world":
        raise BackupError(
            "Backup archive must contain only a "
            "top-level world directory."
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
) -> dict[str, Any]:
    if not _backup_lock.acquire(blocking=False):
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
        backup_path = get_backup_path(filename)

        validation = validate_backup_archive(filename)

        staged_world = _extract_backup_to_staging(
            backup_path,
            staging_directory,
        )

        was_running = minecraft.is_running()

        if was_running:
            stop_result = minecraft.stop()

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
            start_result = minecraft.start()

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
        }

        return result

    except Exception as original_error:
        rollback_errors: list[str] = []

        if live_world_moved:
            if minecraft.is_running():
                stop_result = minecraft.stop()

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
                restart_result = minecraft.start()

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
    if not _backup_lock.acquire(blocking=False):
        raise BackupError(
            "Another backup is already running."
        )

    partial_path: Path | None = None

    try:
        world_directory = _world_dir()
        if not world_directory.is_dir():
            raise BackupError(
                f"Minecraft world directory does not exist: "
                f"{world_directory}"
            )

        try:
            _backup_dir().mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as exc:
            raise BackupError(
                f"Could not create the backup directory: {exc}"
            ) from exc

        save_result = minecraft.save_world()

        if not save_result.ok:
            reason = (
                save_result.stderr
                or save_result.stdout
                or "Unknown save error."
            )

            raise BackupError(
                f"World save failed: {reason}"
            )

        timestamp = datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        filename = (
            f"{BACKUP_PREFIX}"
            f"{timestamp}"
            f"{BACKUP_SUFFIX}"
        )

        final_path = _backup_dir() / filename
        partial_path = _backup_dir() / f".{filename}.partial"

        counter = 1

        while final_path.exists() or partial_path.exists():
            filename = (
                f"{BACKUP_PREFIX}"
                f"{timestamp}-{counter}"
                f"{BACKUP_SUFFIX}"
            )

            final_path = _backup_dir() / filename
            partial_path = (
                _backup_dir()
                / f".{filename}.partial"
            )

            counter += 1

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
                f"Could not create the backup archive: {exc}"
            ) from exc

        removed = _remove_old_backups(retention)

        result = _backup_info(final_path)

        result.update(
            {
                "message": (
                    f"Backup {final_path.name} was created "
                    f"successfully."
                ),
                "world_saved": True,
                "save_message": (
                    save_result.stdout
                    or "World save completed."
                ),
                "removed_backups": removed,
            }
        )

        return result

    finally:
        if (
            partial_path is not None
            and partial_path.exists()
        ):
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
        restore_backup(backup.path.name)
        return CommandResult(True, "Backup restored successfully.")
    except BackupError as error:
        return CommandResult(False, stderr=str(error))
