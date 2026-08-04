from __future__ import annotations
import json
from pathlib import Path
from config import MINECRAFT_DIR, WORLD_DIR
from services.system import CommandResult


def _format_size(total: int) -> str:
    value = float(total)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def info() -> list[str]:
    world = WORLD_DIR
    level_name = "world"
    props = MINECRAFT_DIR / "server.properties"
    try:
        for line in props.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("level-name="):
                level_name = line.split("=", 1)[1].strip() or "world"
                world = MINECRAFT_DIR / level_name
                break
    except OSError:
        pass
    exists = world.exists()
    size = directory_size(world)
    lines = [f"Level name: {level_name}", f"Folder: {world}", f"Exists: {'Yes' if exists else 'No'}", f"World size: {_format_size(size)}"]
    level_dat = world / "level.dat"
    lines.append(f"level.dat: {'Present' if level_dat.exists() else 'Missing'}")
    return lines


def detect_components() -> list[str]:
    results: list[str] = []
    checks = [
        ("plugins", "Plugin folder"),
        ("mods", "Mod folder"),
        ("config", "Mod configuration"),
        ("datapacks", "Datapacks folder"),
    ]
    for folder, label in checks:
        path = MINECRAFT_DIR / folder
        if path.exists():
            count = sum(1 for p in path.iterdir() if p.is_file())
            results.append(f"{label}: detected ({count} files)")
    jars = list(MINECRAFT_DIR.glob("*.jar"))
    if jars:
        results.append("Server JARs: " + ", ".join(p.name for p in jars[:4]))
    return results or ["No plugin or mod folders detected."]


def crash_status() -> list[str]:
    crash_dir = MINECRAFT_DIR / "crash-reports"
    if not crash_dir.exists():
        return ["No crash-report folder found."]
    reports = sorted(crash_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        return ["No crash reports found."]
    newest = reports[0]
    return [f"Crash reports: {len(reports)}", f"Newest: {newest.name}"]
