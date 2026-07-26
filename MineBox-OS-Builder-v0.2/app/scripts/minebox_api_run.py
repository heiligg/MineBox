#!/usr/bin/python3
"""Start the MineBox API with optional HTTPS (self-signed TLS)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


TLS_DIR = Path("/var/lib/minebox/tls")
CERT_FILE = TLS_DIR / "cert.pem"
KEY_FILE = TLS_DIR / "key.pem"
ENABLED_FLAG = TLS_DIR / "enabled"


def main() -> int:
    os.environ.setdefault("PYTHONPATH", "/opt/minebox")
    os.chdir("/opt/minebox")

    args = [
        sys.executable,
        "-m",
        "uvicorn",
        "api.server:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
    ]
    if ENABLED_FLAG.is_file() and CERT_FILE.is_file() and KEY_FILE.is_file():
        args.extend(
            [
                "--ssl-certfile",
                str(CERT_FILE),
                "--ssl-keyfile",
                str(KEY_FILE),
            ]
        )
        os.environ["MINEBOX_TLS"] = "1"
    else:
        os.environ.pop("MINEBOX_TLS", None)

    os.execv(sys.executable, args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
