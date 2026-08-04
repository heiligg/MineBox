#!/usr/bin/python3
"""Install/update MineBox Avahi advertisements for dashboard + Minecraft."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


SOURCE = Path("/opt/minebox/services/avahi/minebox.service")
TARGET = Path("/etc/avahi/services/minebox.service")
AVAHI_CONF = Path("/etc/avahi/avahi-daemon.conf")


def _ensure_avahi_iface_policy() -> None:
    """Keep mDNS off the SoftAP radio.

    Windows treats .local as mDNS-only. On MineBox-Setup, multicast DNS is
    unreliable, and advertising the LAN IP (wlan1) to hotspot clients makes
    minebox.local resolve to an unreachable address. LAN clients still get
    minebox.local via wlan1/eth0.
    """
    if not AVAHI_CONF.is_file():
        return
    text = AVAHI_CONF.read_text(encoding="utf-8")
    updated = text
    if re.search(r"^#?deny-interfaces=", updated, flags=re.M):
        updated = re.sub(
            r"^#?deny-interfaces=.*$",
            "deny-interfaces=wlan0",
            updated,
            count=1,
            flags=re.M,
        )
    else:
        updated = updated.replace(
            "[server]\n",
            "[server]\ndeny-interfaces=wlan0\n",
            1,
        )
    if updated != text:
        AVAHI_CONF.write_text(updated, encoding="utf-8")
        subprocess.run(
            ["systemctl", "try-reload-or-restart", "avahi-daemon.service"],
            check=False,
            timeout=30,
        )
        print(f"updated {AVAHI_CONF} deny-interfaces=wlan0")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=25565)
    args = parser.parse_args()

    if not SOURCE.is_file():
        print(f"missing template: {SOURCE}", file=sys.stderr)
        return 1

    body = SOURCE.read_text(encoding="utf-8")
    body = re.sub(
        r"(<type>_minecraft\._tcp</type>\s*<port>)\d+(</port>)",
        rf"\g<1>{int(args.port)}\g<2>",
        body,
        count=1,
    )
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(body, encoding="utf-8")
    print(f"installed {TARGET} (minecraft port {args.port})")
    _ensure_avahi_iface_policy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
