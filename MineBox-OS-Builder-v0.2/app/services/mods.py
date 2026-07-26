from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from services import servers


MODRINTH_API = "https://api.modrinth.com/v2"
CURSEFORGE_API = "https://api.curseforge.com/v1"
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
    "media.forgecdn.net",
    "forgecdn.net",
    "curseforge.com",
)
CURSEFORGE_GAME_ID = 432  # Minecraft
CURSEFORGE_CLASS_MODS = 6
CURSEFORGE_CLASS_BUKKIT = 5
CURSEFORGE_KEY_FILE = Path("/var/lib/minebox/curseforge-api-key")
# CurseForge modLoaderType enum
_CF_LOADER_TYPES = {
    "forge": 1,
    "fabric": 4,
    "quilt": 5,
    "neoforge": 6,
}


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


def _curseforge_loader_type(loader: str | None = None) -> int | None:
    active = _active()
    kind = (loader or active.loader or "vanilla").strip().lower()
    return _CF_LOADER_TYPES.get(kind)


def _project_types(loader: str | None = None) -> list[str]:
    active = _active()
    kind = (loader or active.loader or "vanilla").strip().lower()
    if kind == "paper":
        return ["plugin"]
    return ["mod"]


_CF_KEY_REJECTED = (
    "CurseForge rejected the API key (invalid or rate-limited). "
    "Regenerate at https://console.curseforge.com/, wait about an hour "
    "if you hit rate limits, then paste the new key and save again."
)
_CF_KEY_MISSING = (
    "CurseForge needs an API key. Add a free key from "
    "https://console.curseforge.com/ under Security, or set "
    "MINEBOX_CURSEFORGE_API_KEY."
)


def curseforge_api_key() -> str | None:
    env = os.environ.get("MINEBOX_CURSEFORGE_API_KEY", "").strip()
    if env:
        return env
    try:
        if CURSEFORGE_KEY_FILE.is_file():
            value = CURSEFORGE_KEY_FILE.read_text(encoding="utf-8").strip()
            return value or None
    except OSError:
        return None
    return None


def _ensure_key_dir() -> None:
    CURSEFORGE_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CURSEFORGE_KEY_FILE.parent, 0o755)
    except OSError:
        pass


def set_curseforge_api_key(key: str | None) -> None:
    clean = (key or "").strip()
    _ensure_key_dir()
    if not clean:
        CURSEFORGE_KEY_FILE.unlink(missing_ok=True)
        return
    CURSEFORGE_KEY_FILE.write_text(clean + "\n", encoding="utf-8")
    try:
        os.chmod(CURSEFORGE_KEY_FILE, 0o600)
    except OSError:
        pass


def _cf_http_error_message(error: urllib.error.HTTPError) -> str:
    code = int(getattr(error, "code", 0) or 0)
    if code in {401, 403}:
        return _CF_KEY_REJECTED
    return f"CurseForge request failed: HTTP Error {code}: {error.reason}"


def validate_curseforge_api_key(key: str, *, timeout: int = 30) -> None:
    """Probe CurseForge with the given key; raise ModsError if rejected."""
    clean = (key or "").strip()
    if not clean:
        raise ModsError(_CF_KEY_MISSING)
    req = urllib.request.Request(
        f"{CURSEFORGE_API}/games/{CURSEFORGE_GAME_ID}",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "x-api-key": clean,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response.read(64)
    except urllib.error.HTTPError as error:
        raise ModsError(_cf_http_error_message(error)) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ModsError(f"CurseForge request failed: {error}") from error


def _request(url: str, timeout: int = 45) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )


def _cf_request(url: str, *, api_key: str | None = None) -> urllib.request.Request:
    key = (api_key or curseforge_api_key() or "").strip()
    if not key:
        raise ModsError(_CF_KEY_MISSING)
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "x-api-key": key,
        },
    )


def _load_json(url: str, timeout: int = 45) -> Any:
    try:
        with urllib.request.urlopen(_request(url), timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        raise ModsError(f"Modrinth request failed: {error}") from error


def _load_cf_json(url: str, timeout: int = 45) -> Any:
    try:
        with urllib.request.urlopen(_cf_request(url), timeout=timeout) as response:
            return json.load(response)
    except ModsError:
        raise
    except urllib.error.HTTPError as error:
        raise ModsError(_cf_http_error_message(error)) from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        raise ModsError(f"CurseForge request failed: {error}") from error


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
    loaders = _modrinth_loaders()
    return {
        "server_id": active.server_id,
        "server_name": active.name,
        "loader": active.loader,
        "version": active.version,
        "target_folder": folder,
        "installed": installed,
        "supports_modrinth": bool(loaders),
        "supports_curseforge": bool(loaders) or active.loader == "paper",
        "curseforge_configured": bool(curseforge_api_key()),
    }


def search(
    query: str,
    *,
    limit: int = 20,
    provider: str = "modrinth",
) -> dict[str, Any]:
    kind = (provider or "modrinth").strip().lower()
    if kind in {"curseforge", "curse", "cf"}:
        return search_curseforge(query, limit=limit)
    return search_modrinth(query, limit=limit)


def search_modrinth(
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
                "provider": "modrinth",
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
        "provider": "modrinth",
        "query": query,
        "total": int(payload.get("total_hits") or len(results))
        if isinstance(payload, dict)
        else len(results),
        "results": results,
        **context(),
    }


def search_curseforge(
    query: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    active = _active()
    query = (query or "").strip()
    if not query:
        raise ModsError("Enter a search term.")
    limit = max(1, min(int(limit), 40))

    class_id = (
        CURSEFORGE_CLASS_BUKKIT
        if (active.loader or "").lower() == "paper"
        else CURSEFORGE_CLASS_MODS
    )
    params: dict[str, str] = {
        "gameId": str(CURSEFORGE_GAME_ID),
        "searchFilter": query,
        "pageSize": str(limit),
        "classId": str(class_id),
        "sortField": "2",  # Popularity
        "sortOrder": "desc",
    }
    if active.version:
        params["gameVersion"] = str(active.version)
    loader_type = _curseforge_loader_type()
    if loader_type is not None:
        params["modLoaderType"] = str(loader_type)

    url = f"{CURSEFORGE_API}/mods/search?{urllib.parse.urlencode(params)}"
    payload = _load_cf_json(url)
    data = payload.get("data") if isinstance(payload, dict) else []
    results: list[dict[str, Any]] = []
    for hit in data or []:
        if not isinstance(hit, dict):
            continue
        mod_id = hit.get("id")
        if mod_id is None:
            continue
        logo = hit.get("logo") if isinstance(hit.get("logo"), dict) else {}
        results.append(
            {
                "provider": "curseforge",
                "project_id": str(mod_id),
                "slug": hit.get("slug"),
                "title": hit.get("name") or hit.get("slug") or "Unknown",
                "description": hit.get("summary") or "",
                "downloads": hit.get("downloadCount") or 0,
                "icon_url": logo.get("thumbnailUrl") or logo.get("url"),
                "categories": [
                    item.get("name")
                    for item in (hit.get("categories") or [])
                    if isinstance(item, dict) and item.get("name")
                ],
                "project_type": "mod",
            }
        )
    return {
        "ok": True,
        "provider": "curseforge",
        "query": query,
        "total": len(results),
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


def install_project(
    project_id: str,
    *,
    version_id: str | None = None,
    provider: str = "modrinth",
) -> dict[str, Any]:
    kind = (provider or "modrinth").strip().lower()
    if kind in {"curseforge", "curse", "cf"}:
        return install_curseforge(project_id, file_id=version_id)
    return install_modrinth(project_id, version_id=version_id)


def install_modrinth(project_id: str, *, version_id: str | None = None) -> dict[str, Any]:
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
        "provider": "modrinth",
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


def _cf_file_matches(file_info: dict[str, Any], *, version: str, loader: str) -> bool:
    game_versions = [
        str(item).lower()
        for item in (file_info.get("gameVersions") or [])
        if item is not None
    ]
    version_l = (version or "").strip().lower()
    loader_l = (loader or "").strip().lower()
    if version_l and not any(version_l == item or version_l in item for item in game_versions):
        return False
    if loader_l and loader_l != "paper":
        if not any(loader_l == item for item in game_versions):
            # Some files only list MC version; still allow if loader type matches later.
            pass
    return True


def install_curseforge(
    mod_id: str,
    *,
    file_id: str | None = None,
) -> dict[str, Any]:
    active = _active()
    mod_id = (mod_id or "").strip()
    if not mod_id:
        raise ModsError("A CurseForge mod id is required.")

    chosen: dict[str, Any] | None = None
    if file_id:
        payload = _load_cf_json(
            f"{CURSEFORGE_API}/mods/{urllib.parse.quote(mod_id)}/files/"
            f"{urllib.parse.quote(str(file_id))}"
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict):
            chosen = data
    else:
        params: dict[str, str] = {"pageSize": "50"}
        if active.version:
            params["gameVersion"] = str(active.version)
        loader_type = _curseforge_loader_type()
        if loader_type is not None:
            params["modLoaderType"] = str(loader_type)
        url = (
            f"{CURSEFORGE_API}/mods/{urllib.parse.quote(mod_id)}/files?"
            + urllib.parse.urlencode(params)
        )
        payload = _load_cf_json(url)
        files = payload.get("data") if isinstance(payload, dict) else []
        for item in files or []:
            if not isinstance(item, dict):
                continue
            if item.get("isAvailable") is False:
                continue
            if _cf_file_matches(
                item, version=str(active.version or ""), loader=str(active.loader or "")
            ):
                chosen = item
                break
        if chosen is None and isinstance(files, list) and files:
            first = files[0]
            if isinstance(first, dict):
                chosen = first

    if not chosen:
        raise ModsError(
            "No compatible CurseForge file found for this server's "
            f"loader/version ({active.loader} {active.version})."
        )

    download_url = chosen.get("downloadUrl")
    if not download_url:
        # Some files hide the direct URL — resolve via download-url endpoint.
        fid = chosen.get("id")
        if fid is not None:
            resolved = _load_cf_json(
                f"{CURSEFORGE_API}/mods/{urllib.parse.quote(mod_id)}/files/"
                f"{fid}/download-url"
            )
            download_url = resolved.get("data") if isinstance(resolved, dict) else None
    if not download_url:
        raise ModsError("CurseForge file has no downloadable URL.")

    filename = _safe_filename(str(chosen.get("fileName") or "mod.jar"))
    folder = target_folder_for_loader()
    root = _root()
    destination_dir = root / folder
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / filename
    size = _download_to(str(download_url), destination)

    return {
        "ok": True,
        "provider": "curseforge",
        "installed": {
            "name": filename,
            "path": f"{folder}/{filename}",
            "size": size,
            "project_id": mod_id,
            "version_id": chosen.get("id"),
            "version_number": chosen.get("displayName") or chosen.get("fileName"),
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
            "That host is not allowed. Use Modrinth, CurseForge/ForgeCDN, or GitHub release URLs."
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
