from __future__ import annotations
import shutil
from pathlib import Path
from config import CRASH_REPORT_DIR, MINECRAFT_DIR, SERVER_LOG
from services.system import run


def directory_size(path: Path) -> int:
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                try: total += item.stat().st_size
                except OSError: pass
    except OSError:
        pass
    return total


def human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def world_folders() -> list[tuple[str, str]]:
    result = []
    try:
        for path in sorted(MINECRAFT_DIR.iterdir()):
            if path.is_dir() and (path / "level.dat").exists():
                result.append((path.name, human_size(directory_size(path))))
    except OSError:
        pass
    return result


def software_inventory() -> dict[str, list[str]]:
    output: dict[str, list[str]] = {"plugins": [], "mods": [], "jars": []}
    for key, folder in (("plugins", MINECRAFT_DIR / "plugins"), ("mods", MINECRAFT_DIR / "mods")):
        try: output[key] = sorted(p.name for p in folder.glob("*.jar"))
        except OSError: pass
    try:
        output["jars"] = sorted(p.name for p in MINECRAFT_DIR.glob("*.jar"))
    except OSError:
        pass
    return output


def crash_reports() -> list[Path]:
    try:
        return sorted(CRASH_REPORT_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []


def latest_crash_summary() -> str:
    reports = crash_reports()
    if not reports:
        return "No crash reports found"
    report = reports[0]
    try:
        first = next((line.strip() for line in report.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()), report.name)
    except OSError:
        first = report.name
    return f"{report.name}: {first[:80]}"


def network_status() -> list[str]:
    route = run(["ip", "route", "show", "default"])
    dns = run(["getent", "hosts", "minecraft.net"], timeout=8)
    return [
        f"Default route: {route.stdout or 'Unavailable'}",
        f"DNS lookup: {'Working' if dns.ok else 'Failed'}",
    ]


def storage_status() -> list[str]:
    disk = shutil.disk_usage(MINECRAFT_DIR if MINECRAFT_DIR.exists() else "/")
    return [
        f"Minecraft folder: {human_size(directory_size(MINECRAFT_DIR))}",
        f"Disk free: {human_size(disk.free)}",
        f"Disk total: {human_size(disk.total)}",
    ]


def log_has_recent_error() -> bool:
    try:
        tail = SERVER_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()[-200:]
        return any("[ERROR]" in line or "Exception" in line for line in tail)
    except OSError:
        return False
