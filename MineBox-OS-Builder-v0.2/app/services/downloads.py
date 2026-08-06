from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from services import servers


VERSION_MANIFEST_URL = (
    "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
)
PAPER_PROJECT_URL = "https://api.papermc.io/v2/projects/paper"
FABRIC_GAME_URL = "https://meta.fabricmc.net/v2/versions/game"
FABRIC_LOADER_URL = "https://meta.fabricmc.net/v2/versions/loader"
FABRIC_INSTALLER_URL = "https://meta.fabricmc.net/v2/versions/installer"
FORGE_PROMOS_URL = (
    "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
)
FORGE_MAVEN_METADATA = (
    "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
)
NEOFORGE_VERSIONS_API = (
    "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
)
NEOFORGE_MAVEN_BASE = (
    "https://maven.neoforged.net/releases/net/neoforged/neoforge"
)

USER_AGENT = "MineBox/0.2 (+https://github.com/heiligg/MineBox)"


class DownloadError(RuntimeError):
    pass


def _request(url: str, timeout: int = 60) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )


def _load_json(url: str, timeout: int = 45) -> Any:
    try:
        with urllib.request.urlopen(_request(url), timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise DownloadError(f"Could not retrieve {url}: {error}") from error


def _load_text(url: str, timeout: int = 45) -> str:
    try:
        with urllib.request.urlopen(_request(url), timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise DownloadError(f"Could not retrieve {url}: {error}") from error


def _download_bytes(
    url: str,
    destination: Path,
    *,
    expected_sha1: str | None = None,
    timeout: int = 300,
) -> int:
    digest = hashlib.sha1()
    total_bytes = 0
    temporary = destination.with_suffix(destination.suffix + ".download")
    temporary.unlink(missing_ok=True)

    try:
        with urllib.request.urlopen(_request(url), timeout=timeout) as response:
            with temporary.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    total_bytes += len(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        temporary.unlink(missing_ok=True)
        raise DownloadError(f"Download failed: {error}") from error

    if expected_sha1 and digest.hexdigest().lower() != expected_sha1.lower():
        temporary.unlink(missing_ok=True)
        raise DownloadError("The downloaded file failed its integrity check.")

    temporary.replace(destination)
    return total_bytes


def _java_for(version_id: str) -> str:
    from services.launcher import _find_java

    try:
        return _find_java(version_id)
    except RuntimeError as error:
        # Surface as DownloadError so /setup/create returns a useful detail.
        raise DownloadError(str(error)) from error


def version_manifest() -> dict[str, Any]:
    return _load_json(VERSION_MANIFEST_URL)


def available_versions(include_snapshots: bool = False) -> list[dict[str, str]]:
    return available_versions_for_loader("vanilla", include_snapshots=include_snapshots)


def available_versions_for_loader(
    loader: str = "vanilla",
    include_snapshots: bool = False,
) -> list[dict[str, str]]:
    clean = servers.normalize_loader(loader)
    if clean == "vanilla":
        return _vanilla_versions(include_snapshots=include_snapshots)
    if clean == "paper":
        return _paper_versions()
    if clean == "fabric":
        return _fabric_versions()
    if clean == "forge":
        return _forge_versions()
    if clean == "neoforge":
        return _neoforge_versions()
    raise DownloadError(f"Unsupported loader '{loader}'.")


def _vanilla_versions(include_snapshots: bool = False) -> list[dict[str, str]]:
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
                "loader": "vanilla",
                "label": str(version.get("id", "")),
            }
        )
    return versions


def _paper_versions() -> list[dict[str, str]]:
    data = _load_json(PAPER_PROJECT_URL)
    versions: list[dict[str, str]] = []
    for version_id in reversed(list(data.get("versions", []))):
        versions.append(
            {
                "id": str(version_id),
                "type": "release",
                "release_time": "",
                "loader": "paper",
                "label": f"{version_id} (Paper)",
            }
        )
    return versions


def _fabric_versions() -> list[dict[str, str]]:
    data = _load_json(FABRIC_GAME_URL)
    versions: list[dict[str, str]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if entry.get("stable") is False:
            continue
        version_id = str(entry.get("version", "")).strip()
        if not version_id:
            continue
        versions.append(
            {
                "id": version_id,
                "type": "release",
                "release_time": "",
                "loader": "fabric",
                "label": f"{version_id} (Fabric)",
            }
        )
    return versions


def _forge_versions() -> list[dict[str, str]]:
    # Prefer promotions map (recommended builds), fall back to maven metadata.
    versions: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        promos = _load_json(FORGE_PROMOS_URL).get("promos", {})
        ordered_keys = [
            key
            for key in promos
            if str(key).endswith("-recommended")
        ] + [
            key
            for key in promos
            if str(key).endswith("-latest")
        ]
        for key in ordered_keys:
            forge_build = promos[key]
            mc_version = str(key).rsplit("-", 1)[0]
            if mc_version in seen:
                continue
            seen.add(mc_version)
            versions.append(
                {
                    "id": mc_version,
                    "type": "release",
                    "release_time": "",
                    "loader": "forge",
                    "loader_version": str(forge_build),
                    "label": f"{mc_version} (Forge {forge_build})",
                }
            )
    except DownloadError:
        pass

    if versions:
        versions.sort(key=lambda item: _version_key(item["id"]), reverse=True)
        return versions

    metadata = _load_text(FORGE_MAVEN_METADATA)
    root = ElementTree.fromstring(metadata)
    for version_node in root.findall("./versioning/versions/version"):
        full = (version_node.text or "").strip()
        if "-" not in full:
            continue
        mc_version, forge_build = full.split("-", 1)
        if mc_version in seen:
            continue
        seen.add(mc_version)
        versions.append(
            {
                "id": mc_version,
                "type": "release",
                "release_time": "",
                "loader": "forge",
                "loader_version": forge_build,
                "label": f"{mc_version} (Forge {forge_build})",
            }
        )
    versions.sort(key=lambda item: _version_key(item["id"]), reverse=True)
    return versions


def _neoforge_to_mc(nf_version: str) -> str | None:
    """Map a NeoForge artifact version to a Minecraft version id."""
    text = (nf_version or "").strip()
    if not text or text.startswith("0."):
        return None
    base = text.split("+", 1)[0]
    # Drop -beta / -alpha suffixes for the numeric core.
    core = base.split("-", 1)[0]
    parts = [piece for piece in core.split(".") if piece.isdigit()]
    if not parts:
        return None
    major = int(parts[0])
    # Calendar Minecraft (26.x): NeoForge 26.2.0.35-beta → MC 26.2
    if major >= 25:
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}"
        return parts[0]
    # Classic: NeoForge 21.1.x → MC 1.21.1
    if len(parts) >= 2:
        return f"1.{parts[0]}.{parts[1]}"
    return f"1.{parts[0]}"


def _neoforge_versions() -> list[dict[str, str]]:
    payload = _load_json(NEOFORGE_VERSIONS_API)
    raw_versions = payload.get("versions") if isinstance(payload, dict) else []
    if not isinstance(raw_versions, list):
        raise DownloadError("NeoForge version list was incomplete.")

    # Prefer stable builds per Minecraft version; fall back to newest prerelease.
    best_stable: dict[str, str] = {}
    best_any: dict[str, str] = {}
    for entry in raw_versions:
        nf = str(entry or "").strip()
        if not nf:
            continue
        mc = _neoforge_to_mc(nf)
        if not mc:
            continue
        lower = nf.lower()
        is_prerelease = any(
            token in lower for token in ("alpha", "beta", "snapshot", "pre")
        )
        best_any[mc] = nf  # list is chronological; last write wins as newest
        if not is_prerelease:
            best_stable[mc] = nf

    versions: list[dict[str, str]] = []
    for mc in best_any:
        nf = best_stable.get(mc) or best_any[mc]
        versions.append(
            {
                "id": mc,
                "type": "release",
                "release_time": "",
                "loader": "neoforge",
                "loader_version": nf,
                "label": f"{mc} (NeoForge {nf})",
            }
        )
    versions.sort(key=lambda item: _version_key(item["id"]), reverse=True)
    return versions


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.split("."):
        digits = "".join(character for character in piece if character.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _find_version(version_id: str) -> dict[str, Any]:
    manifest = version_manifest()
    for version in manifest.get("versions", []):
        if version.get("id") == version_id:
            return version
    raise DownloadError(f"Minecraft version '{version_id}' was not found.")


def download_server(
    version_id: str,
    server_dir: Path,
    overwrite: bool = False,
    loader: str = "vanilla",
    loader_version: str = "",
) -> dict[str, Any]:
    clean = servers.normalize_loader(loader)
    server_dir.mkdir(parents=True, exist_ok=True)

    if clean == "vanilla":
        return _install_vanilla(version_id, server_dir, overwrite=overwrite)
    if clean == "paper":
        return _install_paper(version_id, server_dir, overwrite=overwrite)
    if clean == "fabric":
        return _install_fabric(
            version_id,
            server_dir,
            overwrite=overwrite,
            loader_version=loader_version,
        )
    if clean == "forge":
        return _install_forge(
            version_id,
            server_dir,
            overwrite=overwrite,
            loader_version=loader_version,
        )
    if clean == "neoforge":
        return _install_neoforge(
            version_id,
            server_dir,
            overwrite=overwrite,
            loader_version=loader_version,
        )
    raise DownloadError(f"Unsupported loader '{loader}'.")


def _install_vanilla(
    version_id: str,
    server_dir: Path,
    *,
    overwrite: bool,
) -> dict[str, Any]:
    server_jar = server_dir / "server.jar"
    if server_jar.exists() and not overwrite:
        raise DownloadError(f"A server.jar already exists for '{server_dir.name}'.")

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

    total_bytes = _download_bytes(
        str(download_url),
        server_jar,
        expected_sha1=str(expected_sha1),
    )
    return {
        "success": True,
        "loader": "vanilla",
        "version": version_id,
        "loader_version": "",
        "main_jar": "server.jar",
        "file": str(server_jar),
        "size_bytes": total_bytes,
        "sha1": str(expected_sha1),
    }


def _install_paper(
    version_id: str,
    server_dir: Path,
    *,
    overwrite: bool,
) -> dict[str, Any]:
    server_jar = server_dir / "server.jar"
    if server_jar.exists() and not overwrite:
        raise DownloadError(f"A server.jar already exists for '{server_dir.name}'.")

    builds = _load_json(f"{PAPER_PROJECT_URL}/versions/{version_id}")
    build_numbers = builds.get("builds") or []
    if not build_numbers:
        raise DownloadError(f"No Paper builds were found for Minecraft {version_id}.")
    build = int(build_numbers[-1])
    detail = _load_json(
        f"{PAPER_PROJECT_URL}/versions/{version_id}/builds/{build}"
    )
    application = detail.get("downloads", {}).get("application") or {}
    name = application.get("name")
    sha256 = application.get("sha256")
    if not name:
        raise DownloadError(f"Paper build metadata for {version_id} is incomplete.")

    url = (
        f"{PAPER_PROJECT_URL}/versions/{version_id}/builds/{build}/downloads/{name}"
    )
    total_bytes = _download_bytes(url, server_jar)
    if sha256:
        digest = hashlib.sha256(server_jar.read_bytes()).hexdigest()
        if digest.lower() != str(sha256).lower():
            server_jar.unlink(missing_ok=True)
            raise DownloadError("The Paper jar failed its integrity check.")

    return {
        "success": True,
        "loader": "paper",
        "version": version_id,
        "loader_version": str(build),
        "main_jar": "server.jar",
        "file": str(server_jar),
        "size_bytes": total_bytes,
        "sha1": "",
    }


def _latest_fabric_loader(version_id: str) -> str:
    loaders = _load_json(f"{FABRIC_LOADER_URL}/{version_id}")
    for entry in loaders:
        loader = entry.get("loader") if isinstance(entry, dict) else None
        if isinstance(loader, dict) and loader.get("stable") and loader.get("version"):
            return str(loader["version"])
    if loaders and isinstance(loaders[0], dict):
        loader = loaders[0].get("loader") or {}
        if loader.get("version"):
            return str(loader["version"])
    raise DownloadError(f"No Fabric loader was found for Minecraft {version_id}.")


def _latest_fabric_installer() -> str:
    installers = _load_json(FABRIC_INSTALLER_URL)
    for entry in installers:
        if isinstance(entry, dict) and entry.get("stable") and entry.get("version"):
            return str(entry["version"])
    if installers and isinstance(installers[0], dict) and installers[0].get("version"):
        return str(installers[0]["version"])
    raise DownloadError("No Fabric installer version was found.")


def _install_fabric(
    version_id: str,
    server_dir: Path,
    *,
    overwrite: bool,
    loader_version: str,
) -> dict[str, Any]:
    launch_jar = server_dir / "fabric-server-launch.jar"
    if launch_jar.exists() and not overwrite:
        raise DownloadError(
            f"A Fabric server already exists for '{server_dir.name}'."
        )

    loader = loader_version.strip() or _latest_fabric_loader(version_id)
    installer_version = _latest_fabric_installer()
    installer_jar = server_dir / "fabric-installer.jar"
    installer_url = (
        "https://maven.fabricmc.net/net/fabricmc/fabric-installer/"
        f"{installer_version}/fabric-installer-{installer_version}.jar"
    )
    _download_bytes(installer_url, installer_jar)

    java = _java_for(version_id)
    command = [
        java,
        "-jar",
        str(installer_jar),
        "server",
        "-mcversion",
        version_id,
        "-loader",
        loader,
        "-downloadMinecraft",
        "-dir",
        str(server_dir),
    ]
    result = subprocess.run(
        command,
        cwd=server_dir,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    installer_jar.unlink(missing_ok=True)
    if result.returncode != 0 or not launch_jar.is_file():
        detail = (result.stderr or result.stdout or "Fabric installer failed.").strip()
        raise DownloadError(detail)

    # Keep a conventional server.jar alias when Minecraft jar exists beside it.
    vanilla_jar = server_dir / "server.jar"
    if not vanilla_jar.is_file():
        # Fabric already downloaded minecraft_server.jar in many versions.
        for candidate in server_dir.glob("minecraft_server*.jar"):
            shutil.copy2(candidate, vanilla_jar)
            break

    return {
        "success": True,
        "loader": "fabric",
        "version": version_id,
        "loader_version": loader,
        "main_jar": "fabric-server-launch.jar",
        "file": str(launch_jar),
        "size_bytes": launch_jar.stat().st_size,
        "sha1": "",
    }


def _resolve_forge_build(version_id: str, loader_version: str) -> str:
    if loader_version.strip():
        build = loader_version.strip()
        prefix = f"{version_id}-"
        if build.startswith(prefix):
            return build[len(prefix) :]
        return build
    promos = _load_json(FORGE_PROMOS_URL).get("promos", {})
    for suffix in ("-recommended", "-latest"):
        key = f"{version_id}{suffix}"
        if key in promos:
            return str(promos[key])
    raise DownloadError(f"No Forge build was found for Minecraft {version_id}.")


def _install_forge(
    version_id: str,
    server_dir: Path,
    *,
    overwrite: bool,
    loader_version: str,
) -> dict[str, Any]:
    forge_build = _resolve_forge_build(version_id, loader_version)
    full = f"{version_id}-{forge_build}"
    marker = server_dir / f"forge-{full}.jar"
    unix_args = list(
        (server_dir / "libraries" / "net" / "minecraftforge" / "forge").glob(
            f"{full}/unix_args.txt"
        )
    )
    if (marker.exists() or unix_args) and not overwrite:
        raise DownloadError(f"A Forge server already exists for '{server_dir.name}'.")

    installer_name = f"forge-{full}-installer.jar"
    installer_jar = server_dir / installer_name
    installer_url = (
        "https://maven.minecraftforge.net/net/minecraftforge/forge/"
        f"{full}/{installer_name}"
    )
    _download_bytes(installer_url, installer_jar, timeout=600)

    java = _java_for(version_id)
    try:
        result = subprocess.run(
            [java, "-jar", str(installer_jar), "--installServer"],
            cwd=server_dir,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        installer_jar.unlink(missing_ok=True)
        raise DownloadError(
            "Forge installer timed out after 15 minutes. "
            "Check internet on the Pi and try again."
        ) from error
    installer_jar.unlink(missing_ok=True)
    # Forge leaves installer logs behind; ignore return code slightly if files exist.
    unix_args = list(
        (server_dir / "libraries" / "net" / "minecraftforge" / "forge").glob(
            f"{full}/unix_args.txt"
        )
    )
    shim = server_dir / f"forge-{full}-shim.jar"
    universal = server_dir / f"forge-{full}-universal.jar"
    plain = server_dir / f"forge-{full}.jar"

    main_jar = "server.jar"
    if unix_args:
        main_jar = f"@{unix_args[0].relative_to(server_dir).as_posix()}"
        (server_dir / ".minebox-forge-args").write_text(
            str(unix_args[0].relative_to(server_dir)).replace("\\", "/") + "\n",
            encoding="utf-8",
        )
    elif shim.is_file():
        main_jar = shim.name
        (server_dir / ".minebox-forge-jar").write_text(shim.name + "\n", encoding="utf-8")
    elif plain.is_file():
        # Keep the Forge jar as the launch target. Do NOT replace server.jar —
        # the installer often leaves a vanilla jar there, and launching that
        # makes Minecraft report brand "vanilla".
        main_jar = plain.name
        (server_dir / ".minebox-forge-jar").write_text(plain.name + "\n", encoding="utf-8")
    elif universal.is_file():
        main_jar = universal.name
        (server_dir / ".minebox-forge-jar").write_text(
            universal.name + "\n", encoding="utf-8"
        )
    else:
        # Broader search for forge-*.jar after install.
        candidates = [
            path
            for path in sorted(server_dir.glob(f"forge-{version_id}-*.jar"))
            if "installer" not in path.name.lower()
        ]
        if not candidates:
            candidates = [
                path
                for path in sorted(server_dir.glob("forge-*.jar"))
                if "installer" not in path.name.lower()
            ]
        if candidates:
            main_jar = candidates[0].name
            (server_dir / ".minebox-forge-jar").write_text(
                main_jar + "\n", encoding="utf-8"
            )
        elif result.returncode != 0:
            detail = (
                result.stderr or result.stdout or "Forge installer failed."
            ).strip()
            raise DownloadError(detail)
        else:
            raise DownloadError(
                "Forge installed, but MineBox could not find a launchable Forge jar."
            )

    # Official Forge launch files: keep run.sh executable and seed JVM memory args.
    run_sh = server_dir / "run.sh"
    if run_sh.is_file():
        try:
            os.chmod(run_sh, 0o755)
        except OSError:
            pass

    user_jvm = server_dir / "user_jvm_args.txt"
    if not user_jvm.is_file():
        user_jvm.write_text(
            "# JVM arguments for Forge\n-Xms2G\n-Xmx2G\n",
            encoding="utf-8",
        )

    return {
        "success": True,
        "loader": "forge",
        "version": version_id,
        "loader_version": forge_build,
        "main_jar": main_jar,
        "file": str(
            server_dir
            / (
                unix_args[0]
                if main_jar.startswith("@")
                else main_jar
            )
        ),
        "size_bytes": 0,
        "sha1": "",
    }


def _resolve_neoforge_build(version_id: str, loader_version: str) -> str:
    requested = (loader_version or "").strip()
    if requested:
        return requested
    for entry in _neoforge_versions():
        if entry.get("id") == version_id and entry.get("loader_version"):
            return str(entry["loader_version"])
    raise DownloadError(f"No NeoForge build was found for Minecraft {version_id}.")


def _install_neoforge(
    version_id: str,
    server_dir: Path,
    *,
    overwrite: bool,
    loader_version: str,
) -> dict[str, Any]:
    nf_version = _resolve_neoforge_build(version_id, loader_version)
    unix_args = list(
        (server_dir / "libraries" / "net" / "neoforged" / "neoforge").glob(
            f"{nf_version}/unix_args.txt"
        )
    )
    plain = server_dir / f"neoforge-{nf_version}.jar"
    if (plain.exists() or unix_args) and not overwrite:
        raise DownloadError(
            f"A NeoForge server already exists for '{server_dir.name}'."
        )

    installer_name = f"neoforge-{nf_version}-installer.jar"
    installer_jar = server_dir / installer_name
    installer_url = f"{NEOFORGE_MAVEN_BASE}/{nf_version}/{installer_name}"
    _download_bytes(installer_url, installer_jar, timeout=600)

    java = _java_for(version_id)
    try:
        result = subprocess.run(
            [java, "-jar", str(installer_jar), "--installServer"],
            cwd=server_dir,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        installer_jar.unlink(missing_ok=True)
        raise DownloadError(
            "NeoForge installer timed out after 15 minutes. "
            "Check internet on the Pi and try again."
        ) from error
    installer_jar.unlink(missing_ok=True)

    unix_args = list(
        (server_dir / "libraries" / "net" / "neoforged" / "neoforge").glob(
            f"{nf_version}/unix_args.txt"
        )
    )
    if not unix_args:
        unix_args = list(
            (server_dir / "libraries" / "net" / "neoforged").rglob("unix_args.txt")
        )
    shim = server_dir / f"neoforge-{nf_version}-shim.jar"
    plain = server_dir / f"neoforge-{nf_version}.jar"

    main_jar = "server.jar"
    if unix_args:
        main_jar = f"@{unix_args[0].relative_to(server_dir).as_posix()}"
        (server_dir / ".minebox-forge-args").write_text(
            str(unix_args[0].relative_to(server_dir)).replace("\\", "/") + "\n",
            encoding="utf-8",
        )
    elif shim.is_file():
        main_jar = shim.name
        (server_dir / ".minebox-forge-jar").write_text(shim.name + "\n", encoding="utf-8")
    elif plain.is_file():
        main_jar = plain.name
        (server_dir / ".minebox-forge-jar").write_text(plain.name + "\n", encoding="utf-8")
    else:
        candidates = [
            path
            for path in sorted(server_dir.glob("neoforge-*.jar"))
            if "installer" not in path.name.lower()
        ]
        if candidates:
            main_jar = candidates[0].name
            (server_dir / ".minebox-forge-jar").write_text(
                main_jar + "\n", encoding="utf-8"
            )
        elif result.returncode != 0:
            detail = (
                result.stderr or result.stdout or "NeoForge installer failed."
            ).strip()
            raise DownloadError(detail)
        else:
            raise DownloadError(
                "NeoForge installed, but MineBox could not find a launchable jar."
            )

    run_sh = server_dir / "run.sh"
    if run_sh.is_file():
        try:
            os.chmod(run_sh, 0o755)
        except OSError:
            pass

    user_jvm = server_dir / "user_jvm_args.txt"
    if not user_jvm.is_file():
        user_jvm.write_text(
            "# JVM arguments for NeoForge\n-Xms2G\n-Xmx2G\n",
            encoding="utf-8",
        )

    return {
        "success": True,
        "loader": "neoforge",
        "version": version_id,
        "loader_version": nf_version,
        "main_jar": main_jar,
        "file": str(
            server_dir
            / (
                unix_args[0]
                if main_jar.startswith("@")
                else main_jar
            )
        ),
        "size_bytes": 0,
        "sha1": "",
    }
