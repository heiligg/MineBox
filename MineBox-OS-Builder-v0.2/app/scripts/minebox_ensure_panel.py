#!/usr/bin/env python3
"""Ensure Waveshare-style HDMI panel + Chromium kiosk are configured.

Idempotent. Safe to run from OTA apply (as root) or manually:
  sudo minebox-ensure-panel
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


VIDEO_MODE = "video=HDMI-A-1:800x480@60"
CMDLINE_CANDIDATES = (
    Path("/boot/firmware/cmdline.txt"),
    Path("/boot/cmdline.txt"),
)
CONFIG_CANDIDATES = (
    Path("/boot/firmware/config.txt"),
    Path("/boot/config.txt"),
)


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def ensure_cmdline_video() -> bool:
    """Force landscape 800x480 on HDMI-A-1; strip fbcon rotate quirks."""
    changed = False
    for path in CMDLINE_CANDIDATES:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").strip()
        parts = text.split()
        # Drop prior rotate / competing HDMI video= lines we manage.
        kept: list[str] = []
        for part in parts:
            low = part.lower()
            if low.startswith("fbcon=rotate"):
                changed = True
                continue
            if low.startswith("video=hdmi-a-1:"):
                if part != VIDEO_MODE:
                    changed = True
                continue
            kept.append(part)
        if VIDEO_MODE not in kept:
            kept.append(VIDEO_MODE)
            changed = True
        # Keep console quieter so printk does not paint over the UI.
        if "quiet" not in kept:
            kept.append("quiet")
            changed = True
        if not any(p.startswith("loglevel=") for p in kept):
            kept.append("loglevel=3")
            changed = True
        new = " ".join(kept) + "\n"
        if new != text + "\n" and new.strip() != text:
            path.write_text(new, encoding="utf-8")
            print(f"Updated {path} for 800x480 HDMI landscape.", flush=True)
            changed = True
        break
    return changed


def ensure_config_hdmi() -> bool:
    changed = False
    for path in CONFIG_CANDIDATES:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        original = text
        # Uncomment / ensure i2c for encoder.
        text = text.replace("#dtparam=i2c_arm=on", "dtparam=i2c_arm=on")
        if "dtparam=i2c_arm=on" not in text:
            text = text.rstrip() + "\n\ndtparam=i2c_arm=on\n"
        # Drop legacy display_rotate that sideways-skews the console.
        text2 = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("display_rotate=") or stripped.startswith("#display_rotate="):
                if stripped.startswith("display_rotate="):
                    changed = True
                    continue
            text2.append(line)
        text = "\n".join(text2) + "\n"
        block = (
            "\n# MineBox Waveshare-class HDMI panel (800x480)\n"
            "hdmi_force_hotplug=1\n"
            "hdmi_group=2\n"
            "hdmi_mode=87\n"
            "hdmi_cvt=800 480 60 6 0 0 0\n"
        )
        if "hdmi_cvt=800 480 60 6 0 0 0" not in text and "hdmi_cvt=800 480" not in text:
            text = text.rstrip() + block
            changed = True
        if text != original:
            path.write_text(text, encoding="utf-8")
            print(f"Updated {path} HDMI panel settings.", flush=True)
            changed = True
        break
    return changed


def ensure_xwrapper() -> bool:
    """Allow the minebox service user to start X without a local login seat."""
    path = Path("/etc/X11/Xwrapper.config")
    desired = "allowed_users=anybody\nneeds_root_rights=yes\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as exc:
        print(f"warning: could not read {path}: {exc}", flush=True)
        return False
    if "allowed_users=anybody" in current and "needs_root_rights=yes" in current:
        return False
    try:
        path.write_text(desired, encoding="utf-8")
        os.chmod(path, 0o644)
        print(f"Wrote {path} for non-console X kiosk.", flush=True)
    except OSError as exc:
        print(f"warning: could not write {path}: {exc}", flush=True)
        return False
    return True


def ensure_vc4_xorg() -> bool:
    path = Path("/etc/X11/xorg.conf.d/99-minebox-vc4.conf")
    desired = (
        'Section "OutputClass"\n'
        '    Identifier "vc4"\n'
        '    MatchDriver "vc4"\n'
        '    Driver "modesetting"\n'
        '    Option "PrimaryGPU" "true"\n'
        "EndSection\n"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as exc:
        print(f"warning: could not read {path}: {exc}", flush=True)
        return False
    if current == desired:
        return False
    try:
        path.write_text(desired, encoding="utf-8")
        print(f"Wrote {path}", flush=True)
    except OSError as exc:
        print(f"warning: could not write {path}: {exc}", flush=True)
        return False
    return True


def ensure_kiosk_scripts_executable() -> None:
    for rel in (
        "/opt/minebox/scripts/minebox_display_session.sh",
        "/opt/minebox/scripts/minebox_kiosk_launch.sh",
    ):
        path = Path(rel)
        if path.is_file():
            try:
                os.chmod(path, 0o755)
            except OSError as exc:
                print(f"warning: chmod {path}: {exc}", flush=True)


def ensure_display_unit() -> None:
    unit = Path("/etc/systemd/system/minebox-display.service")
    source = Path("/opt/minebox/services/minebox-display.service")
    if source.is_file():
        try:
            _run(
                [
                    "install",
                    "-m",
                    "0644",
                    str(source),
                    str(unit),
                ],
                timeout=30,
            )
            _run(["systemctl", "daemon-reload"], timeout=60)
        except Exception as exc:  # noqa: BLE001
            print(f"warning: could not refresh display unit: {exc}", flush=True)
    elif unit.is_file():
        text = unit.read_text(encoding="utf-8")
        original = text
        if "Conflicts=minebox-ui.service" not in text:
            text = text.replace(
                "Wants=minebox-api.service\n",
                "Wants=minebox-api.service\nConflicts=minebox-ui.service\n",
            )
        if "WantedBy=graphical.target" in text and "WantedBy=multi-user.target" not in text:
            text = text.replace(
                "WantedBy=graphical.target",
                "WantedBy=multi-user.target",
            )
        if text != original:
            unit.write_text(text, encoding="utf-8")
            print("Updated minebox-display.service", flush=True)
            _run(["systemctl", "daemon-reload"], timeout=60)

    ensure_kiosk_scripts_executable()
    _run(["systemctl", "reset-failed", "minebox-display.service"], timeout=30)
    _run(["systemctl", "enable", "minebox-display.service"], timeout=30)
    # Free the HDMI framebuffer from curses recovery UI.
    _run(["systemctl", "stop", "minebox-ui.service"], timeout=60)
    result = _run(["systemctl", "restart", "minebox-display.service"], timeout=90)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        print(f"warning: minebox-display restart: {detail[:300]}", flush=True)
    else:
        active = _run(["systemctl", "is-active", "minebox-display.service"], timeout=15)
        print(f"minebox-display: {(active.stdout or '').strip()}", flush=True)


def main() -> int:
    if os.geteuid() != 0:
        print("minebox-ensure-panel must run as root", file=sys.stderr)
        return 2
    reboot_hint = False
    if ensure_cmdline_video():
        reboot_hint = True
    if ensure_config_hdmi():
        reboot_hint = True
    ensure_xwrapper()
    ensure_vc4_xorg()
    ensure_display_unit()
    if reboot_hint:
        print(
            "Panel firmware/cmdline changed — reboot once for orientation + I2C.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
