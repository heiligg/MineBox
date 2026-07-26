#!/usr/bin/python3
"""Ensure a compatible Java runtime exists for a Minecraft / Forge version.

Runs as root (sudo / update apply) when the needed JDK is missing.
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
import urllib.error
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
    subprocess.run(
        ["apt-get", "update"],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    install = subprocess.run(
        ["apt-get", "install", "-y", "--no-install-recommends", *packages],
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    if install.returncode != 0:
        detail = (install.stderr or install.stdout or "").strip()
        if detail:
            print(detail, file=sys.stderr)
        return False
    return True


def _stream_download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)


def _extract_tar_gz(archive: Path, extract_dir: Path) -> Path:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        try:
            tar.extractall(extract_dir, filter="data")
        except TypeError:
            tar.extractall(extract_dir)
    children = [path for path in extract_dir.iterdir() if path.is_dir()]
    if not children:
        raise RuntimeError("archive had no top-level directory")
    return children[0]


def _download_temurin(major: int) -> str:
    arch = _adoptium_arch()
    # Try JDK first — Temurin 8 often has no separate JRE build anymore.
    urls = [
        (
            "https://api.adoptium.net/v3/binary/latest/"
            f"{major}/ga/linux/{arch}/jdk/hotspot/normal/eclipse"
            "?project=jdk"
        ),
        (
            "https://api.adoptium.net/v3/binary/latest/"
            f"{major}/ga/linux/{arch}/jre/hotspot/normal/eclipse"
            "?project=jdk"
        ),
        (
            "https://api.adoptium.net/v3/binary/latest/"
            f"{major}/ga/linux/{arch}/jdk/hotspot/normal/adoptium"
        ),
    ]

    JAVA_ROOT.mkdir(parents=True, exist_ok=True)
    target = JAVA_ROOT / f"temurin-{major}"
    java_path = target / "bin" / "java"
    if java_path.is_file() and os.access(java_path, os.X_OK):
        return str(java_path)

    last_error = "download failed"
    for url in urls:
        with tempfile.TemporaryDirectory(prefix="minebox-java-") as tmp:
            archive = Path(tmp) / "temurin.tar.gz"
            try:
                print(f"Downloading Temurin {major} from Adoptium...", file=sys.stderr)
                _stream_download(url, archive)
                if archive.stat().st_size < 1_000_000:
                    last_error = f"download too small ({archive.stat().st_size} bytes)"
                    continue
                payload = _extract_tar_gz(archive, Path(tmp) / "extract")
            except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, tarfile.TarError) as error:
                last_error = str(error)
                print(f"Temurin download attempt failed: {error}", file=sys.stderr)
                continue

            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(payload), str(target))
            # World-executable so minebox/minecraft service users can run it.
            for path in target.rglob("*"):
                try:
                    if path.is_dir():
                        path.chmod(0o755)
                    elif path.name == "java" or path.suffix == ".so":
                        path.chmod(0o755)
                    else:
                        path.chmod(0o644)
                except OSError:
                    pass
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

    if os.geteuid() != 0:
        raise SystemExit(
            "Root privileges are required to install a missing Java runtime. "
            "Update MineBox (Install Update), or run this script with sudo."
        )

    if max_major is not None and min_major <= 8:
        target_major = 8
    elif max_major is not None and max_major <= 16:
        target_major = 11
    else:
        target_major = min_major

    apt_packages = [f"openjdk-{target_major}-jre-headless"]
    print(
        f"Installing Java {target_major} for MineBox "
        f"(need {min_major}"
        + (f"-{max_major}" if max_major is not None else "+")
        + ")...",
        file=sys.stderr,
    )
    _apt_install(apt_packages)

    existing = find_java(min_major, max_major)
    if existing:
        print(existing)
        return existing

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

    try:
        ensure(args.min, maximum)
    except SystemExit as error:
        message = error.args[0] if error.args else str(error)
        if message and message not in {"0", "1"}:
            print(message, file=sys.stderr)
        code = error.code
        if isinstance(code, int):
            return code
        return 1
    except Exception as error:  # noqa: BLE001
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
