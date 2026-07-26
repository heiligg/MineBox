from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from services import servers


MODRINTH_API = "https://api.modrinth.com/v2"
USER_AGENT = "MineBox/0.2 (+https://github.com/heiligg/MineBox)"
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024
ALLOWED_URL_HOSTS = (
    "cdn.modrinth.com",
    "modrinth.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "mediafilez.forgecdn.net",
    "edge.forgecdn.net",
)


class ModsError(Exception):
    """User-facing mods/plugins install failure."""


def _active() -> Any:
    active = servers.active_server()
    if active is None:
        raise ModsError("No active Minecraft server is configured.")
    return active


def _root() -> Path:
    active = _active()
    root = Path(active.directory).expanduser().resolve()
    if not root.is_dir():
        raise ModsError(f"Server directory is missing: {root}")
    return root


def target_folder_for_loader(loader: str | None = None) -> str:
    active = _active()
    kind = (loader or active.loader or "vanilla").strip().lower()
    if kind == "paper":
        return "plugins"
    if kind in {"fabric", "forge", "quilt", "neoforge"}:
        return "mods"
    return "mods"


def _modrinth_loaders(loader: str | None = None) -> list[str]:
    active = _active()
    kind = (loader or active.loader or "vanilla").strip().lower()
    mapping = {
        "fabric": ["fabric"],
        "forge": ["forge"],
        "quilt": ["quilt", "fabric"],
        "neoforge": ["neoforge"],
        "paper": ["paper", "bukkit", "spigot", "purpur"],
        "vanilla": [],
    }
    return mapping.get(kind, [])


def _project_types(loader: str | None = None) -> list[str]:
    active = _active()
    kind = (loader or active.loader or "vanilla").strip().lower()
    if kind == "paper":
        return ["plugin"]
    return ["mod"]


def _request(url: str, timeout: int = 45) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )


def _load_json(url: str, timeout: int = 45) -> Any:
    try:
        with urllib.request.urlopen(_request(url), timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        raise ModsError(f"Modrinth request failed: {error}") from error


def context() -> dict[str, Any]:
    active = _active()
    folder = target_folder_for_loader()
    root = _root()
    path = root / folder
    installed: list[dict[str, Any]] = []
    if path.is_dir():
        try:
            for item in sorted(path.glob("*.jar"), key=lambda p: p.name.lower()):
                try:
                    size = item.stat().st_size
                except OSError:
                    size = 0
                installed.append(
                    {
                        "name": item.name,
                        "path": f"{folder}/{item.name}",
                        "size": size,
                    }
                )
        except OSError:
            pass
    return {
        "server_id": active.server_id,
        "server_name": active.name,
        "loader": active.loader,
        "version": active.version,
        "target_folder": folder,
        "installed": installed,
        "supports_modrinth": bool(_modrinth_loaders()),
    }


def search(
    query: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    active = _active()
    query = (query or "").strip()
    if not query:
        raise ModsError("Enter a search term.")
    limit = max(1, min(int(limit), 40))

    facets: list[list[str]] = []
    project_types = _project_types()
    facets.append([f"project_type:{item}" for item in project_types])
    if active.version:
        facets.append([f"versions:{active.version}"])
    loaders = _modrinth_loaders()
    if loaders:
        facets.append([f"categories:{item}" for item in loaders])

    params = {
        "query": query,
        "limit": str(limit),
        "index": "relevance",
        "facets": json.dumps(facets),
    }
    url = f"{MODRINTH_API}/search?{urllib.parse.urlencode(params)}"
    payload = _load_json(url)
    hits = payload.get("hits") if isinstance(payload, dict) else []
    results: list[dict[str, Any]] = []
    for hit in hits or []:
        if not isinstance(hit, dict):
            continue
        results.append(
            {
                "project_id": hit.get("project_id") or hit.get("slug"),
                "slug": hit.get("slug"),
                "title": hit.get("title") or hit.get("slug") or "Unknown",
                "description": hit.get("description") or "",
                "downloads": hit.get("downloads") or 0,
                "icon_url": hit.get("icon_url"),
                "categories": hit.get("categories") or [],
                "project_type": hit.get("project_type"),
            }
        )
    return {
        "ok": True,
        "query": query,
        "total": int(payload.get("total_hits") or len(results))
        if isinstance(payload, dict)
        else len(results),
        "results": results,
        **context(),
    }


def _pick_primary_file(version: dict[str, Any]) -> dict[str, Any] | None:
    files = version.get("files") if isinstance(version, dict) else None
    if not isinstance(files, list) or not files:
        return None
    for item in files:
        if isinstance(item, dict) and item.get("primary"):
            return item
    first = files[0]
    return first if isinstance(first, dict) else None


def _safe_filename(name: str) -> str:
    clean = Path(name or "download.jar").name
    clean = re.sub(r"[^\w.\-+() ]+", "_", clean).strip("._ ")
    if not clean.lower().endswith(".jar"):
        clean = f"{clean}.jar" if clean else "download.jar"
    if not clean or clean in {".", ".."}:
        raise ModsError("Invalid download filename.")
    return clean


def _download_to(url: str, destination: Path, *, expected_sha1: str | None = None) -> int:
    digest = hashlib.sha1()
    total = 0
    temporary = destination.with_suffix(destination.suffix + ".download")
    temporary.unlink(missing_ok=True)
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            ),
            timeout=300,
        ) as response:
            with temporary.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise ModsError(
                            f"Download exceeds the {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB limit."
                        )
                    handle.write(chunk)
                    digest.update(chunk)
    except ModsError:
        temporary.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        temporary.unlink(missing_ok=True)
        raise ModsError(f"Download failed: {error}") from error

    if expected_sha1 and digest.hexdigest().lower() != expected_sha1.lower():
        temporary.unlink(missing_ok=True)
        raise ModsError("Downloaded file failed its integrity check.")

    temporary.replace(destination)
    return total


def install_project(project_id: str, *, version_id: str | None = None) -> dict[str, Any]:
    active = _active()
    project_id = (project_id or "").strip()
    if not project_id:
        raise ModsError("A Modrinth project id is required.")

    loaders = _modrinth_loaders()
    params: dict[str, str] = {}
    if active.version:
        params["game_versions"] = json.dumps([active.version])
    if loaders:
        params["loaders"] = json.dumps(loaders)

    if version_id:
        version = _load_json(f"{MODRINTH_API}/version/{urllib.parse.quote(version_id)}")
    else:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        versions = _load_json(
            f"{MODRINTH_API}/project/{urllib.parse.quote(project_id)}/version{query}"
        )
        if not isinstance(versions, list) or not versions:
            raise ModsError(
                "No compatible Modrinth version found for this server's "
                f"loader/version ({active.loader} {active.version})."
            )
        version = versions[0]

    file_info = _pick_primary_file(version if isinstance(version, dict) else {})
    if not file_info or not file_info.get("url"):
        raise ModsError("Modrinth version has no downloadable jar.")

    filename = _safe_filename(str(file_info.get("filename") or "mod.jar"))
    folder = target_folder_for_loader()
    root = _root()
    destination_dir = root / folder
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / filename

    hashes = file_info.get("hashes") if isinstance(file_info.get("hashes"), dict) else {}
    sha1 = hashes.get("sha1") if isinstance(hashes, dict) else None
    size = _download_to(str(file_info["url"]), destination, expected_sha1=sha1)

    return {
        "ok": True,
        "installed": {
            "name": filename,
            "path": f"{folder}/{filename}",
            "size": size,
            "project_id": project_id,
            "version_id": version.get("id") if isinstance(version, dict) else None,
            "version_number": version.get("version_number")
            if isinstance(version, dict)
            else None,
        },
        **context(),
    }


def _validate_direct_url(url: str) -> str:
    clean = (url or "").strip()
    parsed = urllib.parse.urlparse(clean)
    if parsed.scheme not in {"http", "https"}:
        raise ModsError("Only http(s) download URLs are allowed.")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ModsError("Invalid download URL.")
    if not any(host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_URL_HOSTS):
        raise ModsError(
            "That host is not allowed. Use Modrinth, GitHub releases, or ForgeCDN URLs."
        )
    return clean


def install_url(url: str, *, filename: str | None = None) -> dict[str, Any]:
    clean_url = _validate_direct_url(url)
    parsed = urllib.parse.urlparse(clean_url)
    guessed = filename or Path(urllib.parse.unquote(parsed.path)).name or "download.jar"
    safe_name = _safe_filename(guessed)
    folder = target_folder_for_loader()
    root = _root()
    destination_dir = root / folder
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / safe_name
    size = _download_to(clean_url, destination)
    return {
        "ok": True,
        "installed": {
            "name": safe_name,
            "path": f"{folder}/{safe_name}",
            "size": size,
            "source_url": clean_url,
        },
        **context(),
    }
