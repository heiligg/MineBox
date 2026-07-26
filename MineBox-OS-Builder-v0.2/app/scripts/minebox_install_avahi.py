#!/usr/bin/python3
"""Install/update MineBox Avahi advertisements for dashboard + Minecraft."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SOURCE = Path("/opt/minebox/services/avahi/minebox.service")
TARGET = Path("/etc/avahi/services/minebox.service")


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
