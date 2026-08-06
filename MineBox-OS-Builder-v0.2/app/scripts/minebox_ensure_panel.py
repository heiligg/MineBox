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


def ensure_display_unit() -> None:
    unit = Path("/etc/systemd/system/minebox-display.service")
    if unit.is_file():
        text = unit.read_text(encoding="utf-8")
        if "WantedBy=graphical.target" in text and "WantedBy=multi-user.target" not in text:
            text = text.replace(
                "WantedBy=graphical.target",
                "WantedBy=multi-user.target",
            )
            unit.write_text(text, encoding="utf-8")
            print("minebox-display.service now WantedBy=multi-user.target", flush=True)
            _run(["systemctl", "daemon-reload"], timeout=60)

    _run(["systemctl", "reset-failed", "minebox-display.service"], timeout=30)
    _run(["systemctl", "enable", "minebox-display.service"], timeout=30)
    # Best-effort start; missing chromium still fails honestly.
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
    ensure_display_unit()
    if reboot_hint:
        print(
            "Panel firmware/cmdline changed — reboot once for orientation + I2C.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
