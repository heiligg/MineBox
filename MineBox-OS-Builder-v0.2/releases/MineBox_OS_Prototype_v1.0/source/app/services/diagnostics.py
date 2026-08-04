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


def _active_server_dir() -> Path | None:
    try:
        from services import servers

        active = servers.active_server()
    except Exception:
        return None
    if active is None:
        return None
    return Path(active.directory)


def _inventory_root() -> Path:
    active_dir = _active_server_dir()
    if active_dir is not None and active_dir.is_dir():
        return active_dir
    return MINECRAFT_DIR


def world_folders() -> list[tuple[str, str]]:
    result = []
    root = _inventory_root()
    try:
        for path in sorted(root.iterdir()):
            if path.is_dir() and (path / "level.dat").exists():
                result.append((path.name, human_size(directory_size(path))))
    except OSError:
        pass
    return result


def software_inventory() -> dict[str, list[str]]:
    output: dict[str, list[str]] = {"plugins": [], "mods": [], "jars": []}
    root = _inventory_root()
    for key, folder in (("plugins", root / "plugins"), ("mods", root / "mods")):
        try: output[key] = sorted(p.name for p in folder.glob("*.jar"))
        except OSError: pass
    try:
        output["jars"] = sorted(p.name for p in root.glob("*.jar"))
    except OSError:
        pass
    return output


def crash_reports() -> list[Path]:
    dirs: list[Path] = []
    active_dir = _active_server_dir()
    if active_dir is not None:
        dirs.append(active_dir / "crash-reports")
    dirs.append(CRASH_REPORT_DIR)

    reports: list[Path] = []
    seen: set[Path] = set()
    for folder in dirs:
        try:
            for path in folder.glob("*.txt"):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                reports.append(path)
        except OSError:
            continue
    try:
        return sorted(reports, key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return reports


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
    root = _inventory_root()
    disk = shutil.disk_usage(root if root.exists() else "/")
    return [
        f"Minecraft folder: {human_size(directory_size(root))}",
        f"Disk free: {human_size(disk.free)}",
        f"Disk total: {human_size(disk.total)}",
    ]


def log_has_recent_error() -> bool:
    path = SERVER_LOG
    try:
        from services import logs as log_service

        discovered = log_service.minecraft_log_path()
        if discovered is not None:
            path = discovered
    except Exception:
        pass
    try:
        tail = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-200:]
        return any("[ERROR]" in line or "Exception" in line for line in tail)
    except OSError:
        return False
