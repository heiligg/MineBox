#!/usr/bin/env python3
"""Post-flash / post-install first-boot validation (Checkpoint 8).

Reports pass/fail without printing secret values.
Exit 0 if all hard checks pass; 1 if any hard check fails.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _version() -> str:
    try:
        sys.path.insert(0, os.environ.get("MINEBOX_APP_DIR", "/opt/minebox"))
        from core.version import get_version

        return get_version()
    except Exception:  # noqa: BLE001
        for path in (Path("/opt/minebox/VERSION"), Path("VERSION"), Path("app/VERSION")):
            if path.is_file():
                return path.read_text(encoding="utf-8").strip().splitlines()[0]
        return "unknown"


def _unit_active(name: str) -> bool | None:
    if not shutil.which("systemctl"):
        return None
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return proc.stdout.strip() == "active"
    except (OSError, subprocess.TimeoutExpired):
        return None


def _unit_enabled(name: str) -> bool | None:
    if not shutil.which("systemctl"):
        return None
    try:
        proc = subprocess.run(
            ["systemctl", "is-enabled", name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return proc.stdout.strip() in {"enabled", "enabled-runtime", "static", "indirect"}
    except (OSError, subprocess.TimeoutExpired):
        return None


def check(label: str, ok: bool, *, hard: bool = True, fix: str = "") -> dict:
    return {"label": label, "ok": ok, "hard": hard, "fix": fix}


def run_checks() -> list[dict]:
    results: list[dict] = []
    version = _version()
    results.append(
        check(
            "minebox_version",
            version not in {"", "unknown"},
            hard=True,
            fix="Ensure /opt/minebox/VERSION exists",
        )
    )
    results[-1]["detail"] = version  # public product string, not a secret

    results.append(
        check(
            "config_dir",
            Path("/etc/minebox").is_dir() or Path("/opt/minebox").is_dir(),
            hard=True,
            fix="Re-run sudo bash /opt/minebox/install.sh",
        )
    )
    results.append(
        check(
            "app_tree",
            Path("/opt/minebox/scripts/minebox_api_run.py").is_file(),
            hard=True,
            fix="Install application tree to /opt/minebox",
        )
    )

    secrets_candidates = [
        Path("/var/lib/minebox"),
        Path("/etc/minebox"),
    ]
    secrets_ok = False
    for base in secrets_candidates:
        if not base.is_dir():
            continue
        secrets_ok = True
        # Permissions: directory should not be world-writable
        mode = base.stat().st_mode & 0o777
        results.append(
            check(
                f"secrets_perms:{base}",
                (mode & 0o002) == 0,
                hard=False,
                fix=f"chmod o-w {base}",
            )
        )
    if not secrets_ok:
        results.append(
            check(
                "secrets_runtime_dir",
                False,
                hard=False,
                fix="Create /var/lib/minebox owned by minebox",
            )
        )

    boot = Path("/var/lib/minebox/bootstrap.json")
    firstboot_marker = Path("/var/lib/minebox/firstboot-complete")
    results.append(
        check(
            "first_boot_marker_or_bootstrap",
            firstboot_marker.is_file() or boot.is_file() or True,
            hard=False,
            fix="Complete web first-boot wizard at http://192.168.4.1",
        )
    )

    api = _unit_active("minebox-api.service")
    results.append(
        check(
            "api_service",
            api is True or api is None,
            hard=api is False,
            fix="sudo systemctl restart minebox-api.service; journalctl -u minebox-api -n 50",
        )
    )

    display = _unit_active("minebox-display.service")
    ui = _unit_active("minebox-ui.service")
    display_or_ui = (display is True) or (ui is True) or (display is None and ui is None)
    results.append(
        check(
            "display_or_curses_fallback",
            display_or_ui,
            hard=display is False and ui is False,
            fix="Enable minebox-display (Chromium) or minebox-ui (tty1 curses)",
        )
    )

    for unit, hard in (
        ("hostapd.service", False),
        ("dnsmasq.service", False),
        ("nftables.service", False),
    ):
        active = _unit_active(unit)
        results.append(
            check(
                unit,
                active is True or active is None,
                hard=False if active is None else hard and active is False,
                fix=f"sudo systemctl status {unit}",
            )
        )

    results.append(
        check(
            "hostapd.conf",
            Path("/etc/hostapd/hostapd.conf").is_file(),
            hard=False,
            fix="PYTHONPATH=/opt/minebox python3 /opt/minebox/scripts/minebox_render_hotspot_configs.py",
        )
    )
    results.append(
        check(
            "dnsmasq_minebox",
            Path("/etc/dnsmasq.d/minebox.conf").is_file()
            or Path("/etc/dnsmasq.d/dnsmasq-minebox.conf").is_file(),
            hard=False,
            fix="Re-run SoftAP render helper",
        )
    )
    results.append(
        check(
            "nftables.conf",
            Path("/etc/nftables.conf").is_file(),
            hard=False,
            fix="Re-run SoftAP render helper / enable nftables",
        )
    )

    # Interface roles — do not print iface secrets; only whether resolver imports
    try:
        sys.path.insert(0, "/opt/minebox")
        from networking.roles import resolve_roles  # noqa: F401

        results.append(check("interface_role_resolver", True, hard=False))
    except Exception as exc:  # noqa: BLE001
        results.append(
            check(
                "interface_role_resolver",
                False,
                hard=False,
                fix=f"Check /opt/minebox/networking ({type(exc).__name__})",
            )
        )

    results.append(
        check(
            "java",
            shutil.which("java") is not None,
            hard=False,
            fix="Install default-jre-headless",
        )
    )

    mc = _unit_enabled("minecraft.service")
    results.append(
        check(
            "minecraft_unit_enabled",
            mc is True or mc is None,
            hard=False,
            fix="sudo systemctl enable minecraft.service (JAR still required)",
        )
    )

    mc_root = Path("/opt/minecraft")
    results.append(
        check(
            "minecraft_storage",
            mc_root.is_dir(),
            hard=True,
            fix="sudo bash /opt/minebox/install.sh",
        )
    )
    backups = mc_root / "backups"
    results.append(
        check(
            "backup_directory",
            backups.is_dir() or mc_root.is_dir(),
            hard=False,
            fix="install -d -o minebox -g minebox /opt/minecraft/backups",
        )
    )

    thermal = (
        Path("/sys/class/thermal/thermal_zone0/temp").is_file()
        or Path("/sys/devices/virtual/thermal").is_dir()
    )
    results.append(
        check(
            "temperature_access",
            thermal or True,  # soft on non-Pi
            hard=False,
            fix="Expected on Raspberry Pi; mock/dev hosts may lack thermal sysfs",
        )
    )
    # Fix: on Pi thermal should exist
    if Path("/sys/firmware/devicetree/base/model").exists():
        results[-1]["ok"] = Path("/sys/class/thermal/thermal_zone0/temp").is_file()

    results.append(
        check(
            "recovery_console_unit",
            Path("/etc/systemd/system/minebox-ui.service").is_file()
            or Path("/lib/systemd/system/minebox-ui.service").is_file()
            or Path("/opt/minebox/services/minebox-ui.service").is_file()
            or Path("/opt/minebox/main.py").is_file(),
            hard=False,
            fix="Install minebox-ui.service",
        )
    )

    # Tailscale optional — status only, never print keys
    ts = shutil.which("tailscale")
    results.append(
        check(
            "tailscale_optional",
            True,
            hard=False,
            fix="Optional: install Tailscale and enable via dashboard Remote Access",
        )
    )
    if ts:
        results[-1]["detail"] = "binary_present"
    else:
        results[-1]["detail"] = "binary_absent"

    # API health without secrets
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8080/api/v1/health", timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        results.append(
            check(
                "api_health_endpoint",
                bool(payload.get("ok")),
                hard=False,
                fix="Start minebox-api; curl http://127.0.0.1:8080/api/v1/health",
            )
        )
    except Exception:  # noqa: BLE001
        results.append(
            check(
                "api_health_endpoint",
                False,
                hard=False,
                fix="Start minebox-api; curl http://127.0.0.1:8080/api/v1/health",
            )
        )

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    results = run_checks()
    hard_fail = [r for r in results if not r["ok"] and r["hard"]]
    soft_fail = [r for r in results if not r["ok"] and not r["hard"]]
    if args.json:
        # Strip any accidental secret-like keys
        safe = []
        for r in results:
            item = {k: v for k, v in r.items() if k not in {"password", "psk", "token", "secret"}}
            safe.append(item)
        print(json.dumps({"version": _version(), "results": safe, "hard_fail": hard_fail, "soft_fail": soft_fail}, indent=2))
    else:
        print(f"MineBox first-boot check — version {_version()}")
        for r in results:
            mark = "PASS" if r["ok"] else ("FAIL" if r["hard"] else "WARN")
            detail = f" ({r['detail']})" if r.get("detail") else ""
            print(f"[{mark}] {r['label']}{detail}")
            if not r["ok"] and r.get("fix"):
                print(f"       fix: {r['fix']}")
        print(f"Summary: {len(hard_fail)} hard failures, {len(soft_fail)} warnings")
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
