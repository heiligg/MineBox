#!/usr/bin/env python3
"""Narrow privileged helper: set a local account password from stdin.

Usage (root/sudo only):
  printf '%s\\n' "$PASSWORD" | python3 minebox_set_os_password.py minebox

No shell interpolation. Username must be an allowlisted local account.
"""

from __future__ import annotations

import sys

ALLOWLIST = {"minebox"}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: minebox_set_os_password.py <username>", file=sys.stderr)
        return 2
    username = argv[1].strip()
    if username not in ALLOWLIST:
        print("username not allowlisted", file=sys.stderr)
        return 2
    password = sys.stdin.readline().rstrip("\n")
    if len(password) < 12 or len(password) > 200:
        print("invalid password length", file=sys.stderr)
        return 2

    import subprocess

    # chpasswd reads user:password lines from stdin.
    payload = f"{username}:{password}\n"
    result = subprocess.run(
        ["/usr/sbin/chpasswd"],
        input=payload,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("chpasswd failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
