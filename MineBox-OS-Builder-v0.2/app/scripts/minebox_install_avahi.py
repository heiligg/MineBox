#!/usr/bin/python3
"""Install/update MineBox Avahi advertisements for dashboard + Minecraft."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


SOURCE = Path("/opt/minebox/services/avahi/minebox.service")
TARGET = Path("/etc/avahi/services/minebox.service")
AVAHI_CONF = Path("/etc/avahi/avahi-daemon.conf")
HOTSPOT_MARKER = Path("/var/lib/minebox/hotspot_iface")
ROLES_FILE = Path("/var/lib/minebox/network_roles.json")


def _hotspot_iface() -> str:
    try:
        if HOTSPOT_MARKER.is_file():
            name = HOTSPOT_MARKER.read_text(encoding="utf-8").strip()
            if name:
                return name
    except OSError:
        pass
    try:
        data = json.loads(ROLES_FILE.read_text(encoding="utf-8"))
        hotspot = data.get("hotspot") if isinstance(data, dict) else None
        if hotspot:
            return str(hotspot)
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return "wlan0"


def _ensure_avahi_conf(hotspot_iface: str) -> None:
    """Advertise minebox.local on home LAN/Ethernet, not the SoftAP radio."""
    if not AVAHI_CONF.is_file():
        return
    text = AVAHI_CONF.read_text(encoding="utf-8")
    updated = text

    def _set(key: str, value: str) -> None:
        nonlocal updated
        pattern = rf"^#?{re.escape(key)}=.*$"
        line = f"{key}={value}"
        if re.search(pattern, updated, flags=re.M):
            updated = re.sub(pattern, line, updated, count=1, flags=re.M)
        elif "[server]\n" in updated:
            updated = updated.replace("[server]\n", f"[server]\n{line}\n", 1)

    _set("use-ipv4", "yes")
    _set("use-ipv6", "no")
    _set("deny-interfaces", hotspot_iface)

    if updated == text:
        return
    AVAHI_CONF.write_text(updated, encoding="utf-8")
    subprocess.run(
        ["systemctl", "try-reload-or-restart", "avahi-daemon.service"],
        check=False,
        timeout=30,
    )
    print(f"updated {AVAHI_CONF} deny-interfaces={hotspot_iface}")


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
    _ensure_avahi_conf(_hotspot_iface())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
