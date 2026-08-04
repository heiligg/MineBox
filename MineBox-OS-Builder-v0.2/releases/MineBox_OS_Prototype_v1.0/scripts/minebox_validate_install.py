#!/usr/bin/env python3
"""Validate a MineBox appliance installation (Checkpoint 7).

Runs without root for most checks. Exit 0 if OK, 1 if failures, 2 if warnings-only
when --strict is not set and only warnings remain.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


REQUIRED_PATHS = [
    Path("/opt/minebox"),
    Path("/opt/minebox/scripts/minebox_api_run.py"),
    Path("/opt/minecraft"),
    Path("/etc/sudoers.d/minebox"),
]

REQUIRED_UNITS = [
    "minebox-api.service",
    "minebox-ui.service",
    "minebox-captive.service",
    "hostapd.service",
    "dnsmasq.service",
    "nftables.service",
]

OPTIONAL_UNITS = [
    "minebox-display.service",
    "minecraft.service",
]


def check(label: str, ok: bool, *, hard: bool = True, detail: str = "") -> dict:
    return {
        "label": label,
        "ok": ok,
        "hard": hard,
        "detail": detail,
    }


def run_checks() -> list[dict]:
    results: list[dict] = []

    for path in REQUIRED_PATHS:
        results.append(check(f"path:{path}", path.exists(), hard=True))

    for unit in REQUIRED_UNITS:
        unit_path = Path("/etc/systemd/system") / unit
        alt = Path("/lib/systemd/system") / unit
        results.append(
            check(
                f"unit:{unit}",
                unit_path.is_file() or alt.is_file(),
                hard=unit.startswith("minebox-api") or unit in {"hostapd.service", "dnsmasq.service"},
            )
        )

    for unit in OPTIONAL_UNITS:
        unit_path = Path("/etc/systemd/system") / unit
        alt = Path("/lib/systemd/system") / unit
        results.append(
            check(f"optional_unit:{unit}", unit_path.is_file() or alt.is_file(), hard=False)
        )

    results.append(check("python3", shutil.which("python3") is not None, hard=True))
    results.append(check("java", shutil.which("java") is not None, hard=False, detail="JRE"))

    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    results.append(check("chromium", chromium is not None, hard=False))
    results.append(check("xinit", shutil.which("xinit") is not None, hard=False))

    # Config examples / appliance config
    cfg = Path("/etc/minebox/minebox.toml")
    example = Path("/opt/minebox/../config/minebox.example.toml")
    # Prefer packaged example under /opt/minebox if present
    for candidate in (
        Path("/opt/minebox/config/minebox.example.toml"),
        Path("/etc/minebox/minebox.toml"),
    ):
        if candidate.is_file():
            results.append(check(f"config:{candidate}", True, hard=False))
            break
    else:
        results.append(check("config:minebox.toml_or_example", cfg.is_file(), hard=False))

    # Hotspot templates / rendered
    results.append(
        check(
            "hostapd.conf",
            Path("/etc/hostapd/hostapd.conf").is_file(),
            hard=True,
        )
    )
    dnsmasq_ok = (
        Path("/etc/dnsmasq.d/minebox.conf").is_file()
        or Path("/etc/dnsmasq.d/dnsmasq-minebox.conf").is_file()
        or Path("/etc/dnsmasq.d/minebox-dnsmasq.conf").is_file()
    )
    results.append(check("dnsmasq.conf", dnsmasq_ok, hard=True))
    results.append(check("nftables.conf", Path("/etc/nftables.conf").is_file(), hard=True))

    # Users
    try:
        import pwd

        for user in ("minebox", "minecraft"):
            try:
                pwd.getpwnam(user)
                results.append(check(f"user:{user}", True, hard=True))
            except KeyError:
                results.append(check(f"user:{user}", False, hard=True))
    except Exception as exc:  # noqa: BLE001
        results.append(check("user:lookup", False, hard=False, detail=str(exc)))

    # Sudoers content
    sudoers = Path("/etc/sudoers.d/minebox")
    if sudoers.is_file():
        text = sudoers.read_text(encoding="utf-8", errors="replace")
        results.append(
            check(
                "sudoers:hostapd_restart",
                "restart hostapd.service" in text,
                hard=True,
            )
        )
        results.append(
            check(
                "sudoers:render_hotspot",
                "minebox_render_hotspot_configs.py" in text,
                hard=False,
            )
        )
        results.append(
            check("sudoers:nft", "nft -f /etc/nftables.conf" in text, hard=False)
        )

    # Minecraft jar optional
    jar_present = any(Path("/opt/minecraft").rglob("server.jar")) if Path("/opt/minecraft").is_dir() else False
    results.append(
        check(
            "minecraft_server.jar",
            jar_present,
            hard=False,
            detail="Expected missing until first-boot wizard",
        )
    )

    # Corrupt config detection if TOML present
    try:
        os.environ.setdefault("MINEBOX_FORCE_MOCK_HARDWARE", "1")
        app = Path("/opt/minebox")
        if app.is_dir():
            sys.path.insert(0, str(app))
        from core.minebox_config import get_config

        get_config()
        results.append(check("config_validate", True, hard=True))
    except Exception as exc:  # noqa: BLE001
        results.append(check("config_validate", False, hard=False, detail=str(exc)[:200]))

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    args = parser.parse_args(argv)
    results = run_checks()
    hard_fail = [r for r in results if not r["ok"] and r["hard"]]
    soft_fail = [r for r in results if not r["ok"] and not r["hard"]]
    if args.json:
        print(json.dumps({"results": results, "hard_fail": hard_fail, "soft_fail": soft_fail}, indent=2))
    else:
        for r in results:
            mark = "OK" if r["ok"] else ("FAIL" if r["hard"] else "WARN")
            extra = f" — {r['detail']}" if r.get("detail") else ""
            print(f"[{mark}] {r['label']}{extra}")
        print(
            f"Summary: {len(results)} checks, {len(hard_fail)} hard failures, {len(soft_fail)} warnings"
        )
    if hard_fail:
        return 1
    if args.strict and soft_fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
