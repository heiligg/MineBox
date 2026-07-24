#!/usr/bin/env python3
"""Privileged helper used by MineBox to safely change its system hostname."""
from __future__ import annotations

import re
import subprocess
import sys

HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: minebox-set-hostname <hostname>", file=sys.stderr)
        return 2

    hostname = sys.argv[1].strip().lower()
    if not HOST_RE.fullmatch(hostname):
        print("Hostname must use lowercase letters, numbers, and hyphens, and cannot begin or end with a hyphen.", file=sys.stderr)
        return 2

    subprocess.run(["/usr/bin/hostnamectl", "set-hostname", hostname], check=True)
    subprocess.run(["/usr/bin/systemctl", "try-restart", "avahi-daemon.service"], check=False)
    print(f"Hostname changed to {hostname}.local")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
