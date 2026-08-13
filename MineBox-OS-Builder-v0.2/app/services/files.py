from __future__ import annotations

import base64
import shutil
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from services import minecraft
from services import servers


MAX_UPLOAD_BYTES = 256 * 1024 * 1024
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
