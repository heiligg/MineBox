#!/usr/bin/python3
"""Emergency restore of MineBox-Setup internet sharing (NAT + DNS).

Run on the Pi (keyboard or SSH):
  sudo python3 /opt/minebox/scripts/minebox_hotspot_net_restore.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HOTSPOT = Path("/opt/minebox/services/hotspot")
NFT_SRC = HOTSPOT / "minebox-hotspot.nft"
DNS_SRC = HOTSPOT / "dnsmasq-minebox.conf"
SYSCTL_SRC = HOTSPOT / "90-minebox-router.conf"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=False)


def main() -> int:
    if not NFT_SRC.is_file():
        print(f"missing {NFT_SRC}", file=sys.stderr)
        return 1

    raw = NFT_SRC.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    Path("/etc/nftables.conf").write_bytes(raw)

    if DNS_SRC.is_file():
        raw = DNS_SRC.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        Path("/etc/dnsmasq.d/minebox.conf").write_bytes(raw)

    if SYSCTL_SRC.is_file():
        raw = SYSCTL_SRC.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        Path("/etc/sysctl.d/90-minebox-router.conf").write_bytes(raw)

    dropin_dir = Path("/etc/systemd/system/dnsmasq.service.d")
    dropin_dir.mkdir(parents=True, exist_ok=True)
    dropin_src = HOTSPOT / "dnsmasq-minebox.service.dropin"
    dropin_body = (
        dropin_src.read_text(encoding="utf-8")
        if dropin_src.is_file()
        else (
            "[Service]\n"
            "Type=simple\n"
            "ExecStartPre=\n"
            "ExecStartPost=\n"
            "ExecStart=\n"
            "ExecStart=/usr/sbin/dnsmasq -k "
            "--conf-file=/etc/dnsmasq.conf "
            "--conf-dir=/etc/dnsmasq.d,.dpkg-dist,.dpkg-old,.dpkg-new\n"
        )
    )
    (dropin_dir / "minebox.conf").write_text(
        dropin_body.replace("\r\n", "\n"), encoding="utf-8"
    )

    run(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    run(["sysctl", "-w", "net.ipv6.conf.wlan0.disable_ipv6=1"])
    run(["nft", "-f", "/etc/nftables.conf"])
    run(["systemctl", "enable", "--now", "nftables.service"])
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "reset-failed", "dnsmasq.service"])
    run(["systemctl", "restart", "dnsmasq.service"])
    run(["systemctl", "try-restart", "hostapd.service"])
    print("Hotspot NAT/DNS restore complete.")
    print("On your PC: forget MineBox-Setup, reconnect, then open http://192.168.4.1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
