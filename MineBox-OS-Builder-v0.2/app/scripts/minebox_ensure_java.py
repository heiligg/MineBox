#!/usr/bin/python3
"""Ensure a compatible Java runtime exists for a Minecraft / Forge version.

Runs as root (sudo) from the MineBox launcher when the needed JDK is missing.
Uses apt when packages exist; otherwise downloads Eclipse Temurin from Adoptium
into /opt/java (needed for Java 8 on Debian Bookworm / Raspberry Pi OS).
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path


JAVA_ROOT = Path("/opt/java")
USER_AGENT = "MineBox/0.2 (+https://github.com/heiligg/MineBox)"


def _machine() -> str:
    machine = platform.machine().lower()
    if machine in {"aarch64", "arm64"}:
        return "aarch64"
    if machine in {"x86_64", "amd64"}:
        return "x64"
    if machine.startswith("arm"):
        return "arm"
    return machine


def _adoptium_arch() -> str:
    machine = _machine()
    if machine == "aarch64":
        return "aarch64"
    if machine == "x64":
        return "x64"
    if machine == "arm":
        return "arm"
    raise SystemExit(f"Unsupported CPU architecture for Temurin download: {machine}")


def _java_major(java: str) -> int | None:
    try:
        result = subprocess.run(
            [java, "-version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = f"{result.stderr}\n{result.stdout}"
    match = re.search(r'version "(?P<ver>[^"]+)"', text)
    if not match:
        match = re.search(r"version (?P<ver>\d+(\.\d+)*)", text)
    if not match:
        return None
    ver = match.group("ver")
    if ver.startswith("1."):
        pieces = ver.split(".")
        return int(pieces[1]) if len(pieces) > 1 else None
    return int(ver.split(".")[0])


def _candidate_paths(major: int) -> list[Path]:
    machine = _machine()
    arch_suffixes = {
        "aarch64": ["arm64", "aarch64"],
        "x64": ["amd64", "x64"],
        "arm": ["armhf", "arm"],
    }.get(machine, [machine])

    paths: list[Path] = [
        JAVA_ROOT / f"temurin-{major}" / "bin" / "java",
        JAVA_ROOT / f"jdk-{major}" / "bin" / "java",
    ]
    for suffix in arch_suffixes:
        paths.extend(
            [
                Path(f"/usr/lib/jvm/java-{major}-openjdk-{suffix}/bin/java"),
                Path(f"/usr/lib/jvm/temurin-{major}-jdk-{suffix}/bin/java"),
                Path(f"/usr/lib/jvm/temurin-{major}-jre-{suffix}/bin/java"),
            ]
        )
    which = shutil.which("java")
    if which:
        paths.append(Path(which))
    return paths


def find_java(min_major: int, max_major: int | None = None) -> str | None:
    found: list[tuple[int, str]] = []
    seen: set[str] = set()
    for path in _candidate_paths(min_major):
        resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        if not path.is_file() or not os.access(path, os.X_OK):
            continue
        major = _java_major(resolved)
        if major is None:
            continue
        if major < min_major:
            continue
        if max_major is not None and major > max_major:
            continue
        found.append((major, resolved))
    if not found:
        return None
    found.sort(key=lambda item: item[0], reverse=True)
    return found[0][1]


def _apt_install(packages: list[str]) -> bool:
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    update = subprocess.run(
        ["apt-get", "update"],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    if update.returncode != 0:
        print(update.stderr or update.stdout, file=sys.stderr)

    install = subprocess.run(
        ["apt-get", "install", "-y", "--no-install-recommends", *packages],
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    if install.returncode != 0:
        print(install.stderr or install.stdout, file=sys.stderr)
        return False
    return True


def _download_temurin(major: int) -> str:
    arch = _adoptium_arch()
    # Prefer JRE when available; fall back to JDK.
    urls = [
        (
            "https://api.adoptium.net/v3/binary/latest/"
            f"{major}/ga/linux/{arch}/jre/hotspot/normal/eclipse"
            "?project=jdk"
        ),
        (
            "https://api.adoptium.net/v3/binary/latest/"
            f"{major}/ga/linux/{arch}/jdk/hotspot/normal/eclipse"
            "?project=jdk"
        ),
    ]

    JAVA_ROOT.mkdir(parents=True, exist_ok=True)
    target = JAVA_ROOT / f"temurin-{major}"
    if (target / "bin" / "java").is_file():
        return str(target / "bin" / "java")

    last_error = "download failed"
    for url in urls:
        with tempfile.TemporaryDirectory(prefix="minebox-java-") as tmp:
            archive = Path(tmp) / "temurin.tar.gz"
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    archive.write_bytes(response.read())
            except Exception as error:  # noqa: BLE001 - surface download issues
                last_error = str(error)
                continue

            extract_dir = Path(tmp) / "extract"
            extract_dir.mkdir()
            try:
                with tarfile.open(archive, "r:gz") as tar:
                    tar.extractall(extract_dir)
            except (tarfile.TarError, OSError) as error:
                last_error = str(error)
                continue

            children = [path for path in extract_dir.iterdir() if path.is_dir()]
            if not children:
                last_error = "archive had no top-level directory"
                continue
            payload = children[0]
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(payload), str(target))
            java = target / "bin" / "java"
            if java.is_file():
                os.chmod(java, 0o755)
                return str(java)
            last_error = "extracted archive missing bin/java"

    raise SystemExit(f"Could not install Temurin Java {major}: {last_error}")


def ensure(min_major: int, max_major: int | None = None) -> str:
    existing = find_java(min_major, max_major)
    if existing:
        print(existing)
        return existing

    # Choose an install target inside the allowed band.
    if max_major is not None and min_major <= 8:
        target_major = 8
    elif max_major is not None and max_major <= 11:
        target_major = 11
    elif max_major is not None and max_major <= 16:
        target_major = 11
    else:
        target_major = min_major

    apt_packages = [f"openjdk-{target_major}-jre-headless"]
    if target_major >= 17:
        apt_packages.append(f"openjdk-{target_major}-jdk-headless")

    print(
        f"Installing Java {target_major} for MineBox (min={min_major}, "
        f"max={max_major})...",
        file=sys.stderr,
    )
    _apt_install(apt_packages)

    existing = find_java(min_major, max_major)
    if existing:
        print(existing)
        return existing

    # Bookworm often has no OpenJDK 8 — fetch Temurin.
    java = _download_temurin(target_major)
    major = _java_major(java)
    if major is None or major < min_major or (
        max_major is not None and major > max_major
    ):
        raise SystemExit(
            f"Installed Java at {java} is not compatible "
            f"(got {major}, need {min_major}"
            + (f"-{max_major}" if max_major is not None else "+")
            + ")."
        )
    print(java)
    return java


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min", type=int, required=True, help="Minimum Java major")
    parser.add_argument("--max", type=int, default=0, help="Maximum Java major (0=none)")
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Only print an existing Java path; do not install",
    )
    args = parser.parse_args()
    maximum = args.max if args.max > 0 else None

    if args.print_only:
        path = find_java(args.min, maximum)
        if not path:
            return 1
        print(path)
        return 0

    if os.geteuid() != 0 and not find_java(args.min, maximum):
        print(
            "Root privileges are required to install a missing Java runtime.",
            file=sys.stderr,
        )
        return 2

    ensure(args.min, maximum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
