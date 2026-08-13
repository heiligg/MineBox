from __future__ import annotations

import base64
import shutil
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from services import minecraft
from services import servers


MAX_UPLOAD_BYTES = 256 * 1024 * 1024
MAX_WORLD_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
WORLD_SKIP_NAMES = {"session.lock"}
BLOCKED_NAME_PREFIXES = (".minebox-",)
BLOCKED_NAMES = {
    ".minebox-rcon-password",
}
QUICK_DIRS = ("mods", "plugins", "config", "world")


class FilesError(Exception):
    """Raised for user-facing file manager failures."""


def _active_root() -> Path:
    active = servers.active_server()
    if active is None:
        raise FilesError("No active Minecraft server is configured.")
    root = Path(active.directory).expanduser().resolve()
    if not root.is_dir():
        raise FilesError(f"Server directory is missing: {root}")
    return root


def _is_blocked_name(name: str) -> bool:
    clean = name.strip()
    if not clean or clean in {".", ".."}:
        return True
    if clean in BLOCKED_NAMES:
        return True
    return any(clean.startswith(prefix) for prefix in BLOCKED_NAME_PREFIXES)


def _normalize_relative(path: str | None) -> str:
    raw = (path or "").replace("\\", "/").strip().lstrip("/")
    if not raw or raw == ".":
        return ""
    parts: list[str] = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if part == ".." or _is_blocked_name(part):
            raise FilesError("That path is not allowed.")
        parts.append(part)
    return "/".join(parts)


def _resolve_under_root(relative: str | None, *, must_exist: bool = False) -> tuple[Path, Path, str]:
    root = _active_root()
    rel = _normalize_relative(relative)
    target = (root / rel).resolve() if rel else root.resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise FilesError("That path is outside the server folder.") from error
    if must_exist and not target.exists():
        raise FilesError("File or folder not found.")
    return root, target, rel


def _world_guard(relative: str, *, mutating: bool) -> None:
    if not mutating:
        return
    top = relative.split("/", 1)[0] if relative else ""
    if not top.startswith("world"):
        return
    if minecraft.is_running():
        raise FilesError(
            "Stop the Minecraft server before changing world files."
        )


def _entry_payload(root: Path, path: Path) -> dict[str, Any]:
    relative = ""
    if path != root:
        relative = path.relative_to(root).as_posix()
    is_dir = path.is_dir()
    size = 0
    mtime = 0.0
    try:
        stat = path.stat()
        mtime = float(stat.st_mtime)
        if not is_dir:
            size = int(stat.st_size)
    except OSError:
        pass
    return {
        "name": path.name if path != root else "",
        "path": relative,
        "type": "dir" if is_dir else "file",
        "size": size,
        "mtime": mtime,
    }


def list_directory(path: str | None = None) -> dict[str, Any]:
    root, target, relative = _resolve_under_root(path)
    if target.is_file():
        raise FilesError("Path is a file, not a folder.")
    if not target.exists():
        # Allow quick-nav into common dirs that do not exist yet.
        if relative in QUICK_DIRS:
            target.mkdir(parents=True, exist_ok=True)
        else:
            raise FilesError("Folder not found.")

    entries: list[dict[str, Any]] = []
    try:
        children = sorted(
            target.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        )
    except OSError as error:
        raise FilesError(f"Could not read folder: {error}") from error

    for child in children:
        if _is_blocked_name(child.name):
            continue
        if child.is_symlink():
            # Skip symlinks to avoid escaping the sandbox via link targets.
            continue
        entries.append(_entry_payload(root, child))

    active = servers.active_server()
    return {
        "server_id": active.server_id if active else None,
        "server_name": active.name if active else None,
        "root": str(root),
        "path": relative,
        "entries": entries,
        "quick_dirs": list(QUICK_DIRS),
        "server_running": minecraft.is_running(),
    }


def ensure_directory(path: str) -> dict[str, Any]:
    relative = _normalize_relative(path)
    if not relative:
        raise FilesError("Choose a folder name.")
    _world_guard(relative, mutating=True)
    root, target, rel = _resolve_under_root(relative)
    if target.exists():
        if not target.is_dir():
            raise FilesError("A file already exists at that path.")
    else:
        try:
            target.mkdir(parents=True, exist_ok=False)
        except OSError as error:
            raise FilesError(f"Could not create folder: {error}") from error
    return {
        "ok": True,
        "entry": _entry_payload(root, target),
        "path": rel,
    }


def decode_rel_token(token: str | None) -> str:
    """Decode the base64url relative-path token from the uploader."""
    raw = (token or "").strip().replace("-", "+").replace("_", "/")
    if not raw:
        return ""
    raw += "=" * ((4 - len(raw) % 4) % 4)
    try:
        return base64.b64decode(raw).decode("utf-8")
    except (OSError, ValueError, UnicodeDecodeError):
        return ""


def _sanitize_nested_path(*candidates: str | None) -> str:
    """Pick the deepest safe relative path from upload metadata."""
    ranked: list[str] = []
    for raw in candidates:
        text = (raw or "").replace("\\", "/").strip().lstrip("/")
        if not text or text.endswith("/"):
            continue
        parts: list[str] = []
        valid = True
        for part in text.split("/"):
            if not part or part == ".":
                continue
            if part == ".." or _is_blocked_name(part):
                valid = False
                break
            parts.append(part)
        if valid and parts:
            ranked.append("/".join(parts))
    if not ranked:
        raise FilesError("Invalid upload filename.")
    return max(ranked, key=lambda item: (item.count("/"), len(item)))


def _upload_relative(filename: str | None, relative_path: str | None) -> str:
    """Allow nested folder uploads while blocking path escape."""
    return _sanitize_nested_path(relative_path, filename)


async def upload_file(
    directory: str | None,
    upload: UploadFile,
    relative_path: str | None = None,
    extra_paths: list[str] | None = None,
) -> dict[str, Any]:
    nested = _sanitize_nested_path(
        relative_path,
        *(extra_paths or []),
        upload.filename,
    )
    relative_dir = _normalize_relative(directory)
    relative = f"{relative_dir}/{nested}" if relative_dir else nested
    _world_guard(relative, mutating=True)

    root, folder, _ = _resolve_under_root(relative_dir)
    if folder.exists() and not folder.is_dir():
        raise FilesError("Upload target is not a folder.")
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise FilesError(f"Could not prepare upload folder: {error}") from error

    destination = (folder / nested).resolve()
    try:
        destination.relative_to(root)
    except ValueError as error:
        raise FilesError("Upload path is outside the server folder.") from error
    if _is_blocked_name(destination.name):
        raise FilesError("That filename is not allowed.")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise FilesError(f"Could not prepare upload folder: {error}") from error

    total = 0
    tmp_path = destination.with_name(destination.name + ".minebox-upload")
    try:
        with tmp_path.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise FilesError(
                        f"Upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
                    )
                handle.write(chunk)
        tmp_path.replace(destination)
    except FilesError:
        tmp_path.unlink(missing_ok=True)
        raise
    except OSError as error:
        tmp_path.unlink(missing_ok=True)
        raise FilesError(f"Upload failed: {error}") from error
    finally:
        await upload.close()

    return {
        "ok": True,
        "entry": _entry_payload(root, destination),
        "bytes": total,
    }


def download_path(path: str) -> Path:
    _relative = _normalize_relative(path)
    if not _relative:
        raise FilesError("Choose a file to download.")
    _root, target, _rel = _resolve_under_root(_relative, must_exist=True)
    if not target.is_file():
        raise FilesError("Only files can be downloaded.")
    if _is_blocked_name(target.name):
        raise FilesError("That file is not available.")
    return target


def delete_path(path: str) -> dict[str, Any]:
    relative = _normalize_relative(path)
    if not relative:
        raise FilesError("Cannot delete the server root folder.")
    _world_guard(relative, mutating=True)
    root, target, rel = _resolve_under_root(relative, must_exist=True)
    if target == root:
        raise FilesError("Cannot delete the server root folder.")
    if _is_blocked_name(target.name):
        raise FilesError("That path is not allowed.")

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except OSError as error:
        raise FilesError(f"Could not delete: {error}") from error

    return {"ok": True, "deleted": rel}


def find_world_root(staging: Path) -> Path:
    """Return the folder that contains level.dat inside an extracted save."""
    direct = staging / "level.dat"
    if direct.is_file():
        return staging
    matches = sorted(
        (path.parent for path in staging.rglob("level.dat") if path.is_file()),
        key=lambda path: len(path.relative_to(staging).parts),
    )
    if not matches:
        raise FilesError(
            "That file is not a Minecraft world save (missing level.dat). "
            "Zip the folder inside .minecraft/saves, not the saves folder itself."
        )
    return matches[0]


def _safe_extract_zip(archive: Path, dest: Path) -> None:
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/").lstrip("/")
            if not name or name.endswith("/"):
                continue
            parts = Path(name).parts
            if any(part in {".", ".."} or part.startswith("/") for part in parts):
                raise FilesError("World zip contains an unsafe path.")
            target = (dest / name).resolve()
            try:
                target.relative_to(dest)
            except ValueError as error:
                raise FilesError("World zip contains an unsafe path.") from error
            if Path(name).name in WORLD_SKIP_NAMES:
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as source, target.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
            except OSError as error:
                raise FilesError(f"Could not extract world zip: {error}") from error


def _safe_extract_tar(archive: Path, dest: Path) -> None:
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, mode="r:*") as tar:
        for member in tar.getmembers():
            name = member.name.replace("\\", "/").lstrip("/")
            if not member.isfile() or not name:
                continue
            parts = Path(name).parts
            if any(part in {".", ".."} for part in parts):
                raise FilesError("World archive contains an unsafe path.")
            target = (dest / name).resolve()
            try:
                target.relative_to(dest)
            except ValueError as error:
                raise FilesError("World archive contains an unsafe path.") from error
            if Path(name).name in WORLD_SKIP_NAMES:
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = tar.extractfile(member)
                if extracted is None:
                    continue
                with extracted, target.open("wb") as handle:
                    shutil.copyfileobj(extracted, handle)
            except OSError as error:
                raise FilesError(f"Could not extract world archive: {error}") from error


def _copy_world(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if child.name in WORLD_SKIP_NAMES or _is_blocked_name(child.name):
            continue
        target = dest / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        elif child.is_file():
            shutil.copy2(child, target)


async def install_world_save(upload: UploadFile) -> dict[str, Any]:
    """Replace the active multiplayer world with a zipped singleplayer save."""
    filename = (upload.filename or "world.zip").lower()
    root = _active_root()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    incoming = root / f".minebox-world-upload-{stamp}"
    staging = root / f".minebox-world-extract-{stamp}"
    live_world = root / "world"
    backup_world = root / f"world.bak-{stamp}"

    incoming.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with incoming.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_WORLD_UPLOAD_BYTES:
                    raise FilesError(
                        "World upload exceeds the "
                        f"{MAX_WORLD_UPLOAD_BYTES // (1024 * 1024)} MB limit."
                    )
                handle.write(chunk)
    except FilesError:
        incoming.unlink(missing_ok=True)
        raise
    except OSError as error:
        incoming.unlink(missing_ok=True)
        raise FilesError(f"Could not save world upload: {error}") from error
    finally:
        await upload.close()

    if total < 32:
        incoming.unlink(missing_ok=True)
        raise FilesError("That world upload was empty.")

    was_running = minecraft.is_running()
    try:
        if filename.endswith(".tar.gz") or filename.endswith(".tgz"):
            _safe_extract_tar(incoming, staging)
        else:
            try:
                _safe_extract_zip(incoming, staging)
            except zipfile.BadZipFile as error:
                raise FilesError(
                    "That file is not a zip. On Windows, right-click the save "
                    "folder in .minecraft\\saves and choose Send to → "
                    "Compressed (zipped) folder, then upload the .zip."
                ) from error

        world_root = find_world_root(staging)
        if not (world_root / "region").is_dir():
            raise FilesError(
                "That save is missing its region folder. Zip the world folder "
                "itself (the one that contains level.dat), not only some of the files."
            )

        if was_running:
            stop = minecraft.stop_service()
            if not stop.ok:
                raise FilesError(
                    "Could not stop Minecraft before replacing the world: "
                    + (stop.stderr or stop.stdout or "unknown error")
                )

        if live_world.exists():
            if backup_world.exists():
                shutil.rmtree(backup_world, ignore_errors=True)
            live_world.rename(backup_world)

        try:
            _copy_world(world_root, live_world)
        except OSError as error:
            raise FilesError(f"Could not install the world: {error}") from error
        if not (live_world / "level.dat").is_file() or not (live_world / "region").is_dir():
            raise FilesError("World install failed verification.")
    except Exception:
        incoming.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
        raise

    incoming.unlink(missing_ok=True)
    shutil.rmtree(staging, ignore_errors=True)

    listing = list_directory("")
    return {
        "ok": True,
        "bytes": total,
        "world": "world",
        "backup": backup_world.name if backup_world.exists() else None,
        "server_stopped": was_running,
        "message": (
            "Singleplayer save installed as the multiplayer world. "
            + (
                f"The previous world was kept as {backup_world.name}. "
                if backup_world.exists()
                else ""
            )
            + "Start the server to play it."
        ),
        **listing,
    }
