#!/usr/bin/python3
"""Privileged helper: install, start, and stop the playit.gg agent."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path


PLAYIT_VERSION = "v1.0.10"
DATA_DIR = Path("/var/lib/minebox/playit")
BIN = DATA_DIR / "playit"
UNIT_SRC = Path("/opt/minebox/services/minebox-playit.service")
UNIT_DST = Path("/etc/systemd/system/minebox-playit.service")
LOG = DATA_DIR / "playit.log"


def _run(command: list[str], timeout: int = 120) -> int:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


def _binary_name() -> str:
    machine = os.uname().machine.lower()
    if machine in {"aarch64", "arm64"}:
        return "playit-linux-aarch64"
    if machine in {"x86_64", "amd64"}:
        return "playit-linux-amd64"
    if machine.startswith("armv7") or machine == "armv7l":
        return "playit-linux-armv7"
    raise SystemExit(f"Unsupported architecture for playit.gg: {machine}")


def _download() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DATA_DIR, 0o755)
    name = _binary_name()
    url = (
        "https://github.com/playit-cloud/playit-agent/releases/download/"
        f"{PLAYIT_VERSION}/{name}"
    )
    temporary = DATA_DIR / ".playit.download"
    urllib.request.urlretrieve(url, temporary)
    temporary.replace(BIN)
    os.chmod(BIN, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
    shutil.chown(DATA_DIR, user="minebox", group="minebox")
    shutil.chown(BIN, user="minebox", group="minebox")


def _install_unit() -> None:
    if UNIT_SRC.is_file():
        shutil.copyfile(UNIT_SRC, UNIT_DST)
    else:
        UNIT_DST.write_text(
            "[Unit]\n"
            "Description=MineBox playit.gg internet tunnel\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            "User=minebox\n"
            "Group=minebox\n"
            "WorkingDirectory=/var/lib/minebox/playit\n"
            "ExecStart=/var/lib/minebox/playit/playit\n"
            "Restart=always\n"
            "RestartSec=5\n"
            "StandardOutput=append:/var/lib/minebox/playit/playit.log\n"
            "StandardError=append:/var/lib/minebox/playit/playit.log\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n",
            encoding="utf-8",
        )
    os.chmod(UNIT_DST, 0o644)
    _run(["/usr/bin/systemctl", "daemon-reload"], timeout=30)


def cmd_ensure() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not BIN.is_file():
        _download()
    if not LOG.exists():
        LOG.write_text("", encoding="utf-8")
    shutil.chown(DATA_DIR, user="minebox", group="minebox")
    try:
        shutil.chown(LOG, user="minebox", group="minebox")
    except OSError:
        pass
    _install_unit()
    code = _run(["/usr/bin/systemctl", "enable", "--now", "minebox-playit.service"], timeout=30)
    return code


def cmd_stop() -> int:
    return _run(["/usr/bin/systemctl", "stop", "minebox-playit.service"], timeout=30)


def cmd_disable() -> int:
    _run(["/usr/bin/systemctl", "stop", "minebox-playit.service"], timeout=30)
    return _run(["/usr/bin/systemctl", "disable", "minebox-playit.service"], timeout=30)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: minebox_playit.py ensure|stop|disable", file=sys.stderr)
        return 2
    action = sys.argv[1].strip().lower()
    if action == "ensure":
        return cmd_ensure()
    if action == "stop":
        return cmd_stop()
    if action == "disable":
        return cmd_disable()
    print(f"unknown action: {action}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
