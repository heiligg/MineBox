from __future__ import annotations

import hashlib
import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


VERSION_MANIFEST_URL = (
    "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
)


class DownloadError(RuntimeError):
    pass


def _load_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MineBox/0.2",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise DownloadError(f"Could not retrieve Minecraft information: {error}") from error


def version_manifest() -> dict[str, Any]:
    return _load_json(VERSION_MANIFEST_URL)


def available_versions(include_snapshots: bool = False) -> list[dict[str, str]]:
    manifest = version_manifest()
    versions: list[dict[str, str]] = []

    for version in manifest.get("versions", []):
        version_type = version.get("type", "")

        if not include_snapshots and version_type != "release":
            continue

        versions.append(
            {
                "id": str(version.get("id", "")),
                "type": str(version_type),
                "release_time": str(version.get("releaseTime", "")),
            }
        )

    return versions


def _find_version(version_id: str) -> dict[str, Any]:
    manifest = version_manifest()

    for version in manifest.get("versions", []):
        if version.get("id") == version_id:
            return version

    raise DownloadError(f"Minecraft version '{version_id}' was not found.")


def _download_file(url: str, destination: Path, expected_sha1: str) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "MineBox/0.2"})
    digest = hashlib.sha1()
    total_bytes = 0

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with destination.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    total_bytes += len(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        destination.unlink(missing_ok=True)
        raise DownloadError(f"Server download failed: {error}") from error

    actual_sha1 = digest.hexdigest()
    if actual_sha1.lower() != expected_sha1.lower():
        destination.unlink(missing_ok=True)
        raise DownloadError("The downloaded server file failed its integrity check.")

    return total_bytes


def download_server(
    version_id: str,
    server_dir: Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    server_dir.mkdir(parents=True, exist_ok=True)
    server_jar = server_dir / "server.jar"
    temporary_jar = server_dir / "server.jar.download"

    if server_jar.exists() and not overwrite:
        raise DownloadError(
            f"A server.jar already exists for '{server_dir.name}'."
        )

    version = _find_version(version_id)
    metadata_url = version.get("url")
    if not metadata_url:
        raise DownloadError(f"No metadata URL was supplied for Minecraft {version_id}.")

    metadata = _load_json(str(metadata_url))
    server_download = metadata.get("downloads", {}).get("server")
    if not server_download:
        raise DownloadError(
            f"Minecraft {version_id} does not provide a downloadable server."
        )

    download_url = server_download.get("url")
    expected_sha1 = server_download.get("sha1")
    if not download_url or not expected_sha1:
        raise DownloadError(
            f"Download information for Minecraft {version_id} is incomplete."
        )

    temporary_jar.unlink(missing_ok=True)
    total_bytes = _download_file(
        url=str(download_url),
        destination=temporary_jar,
        expected_sha1=str(expected_sha1),
    )
    shutil.move(str(temporary_jar), str(server_jar))

    return {
        "success": True,
        "version": version_id,
        "file": str(server_jar),
        "size_bytes": total_bytes,
        "sha1": str(expected_sha1),
    }
