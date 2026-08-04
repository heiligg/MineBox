#!/usr/bin/python3
"""Generate and manage MineBox dashboard TLS certificates.

Self-signed certs live in /var/lib/minebox/tls/. When enabled, minebox-api
serves HTTPS on the same port using these files.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path


TLS_DIR = Path("/var/lib/minebox/tls")
CERT_FILE = TLS_DIR / "cert.pem"
KEY_FILE = TLS_DIR / "key.pem"
ENABLED_FLAG = TLS_DIR / "enabled"


def _hostname() -> str:
    try:
        return socket.gethostname().strip() or "minebox"
    except OSError:
        return "minebox"


def _ip_addresses() -> list[str]:
    addresses: list[str] = ["127.0.0.1"]
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            addr = info[4][0]
            if ":" in addr:
                continue
            if addr not in addresses:
                addresses.append(addr)
    except OSError:
        pass
    return addresses


def status() -> dict[str, object]:
    return {
        "enabled": ENABLED_FLAG.is_file() and CERT_FILE.is_file() and KEY_FILE.is_file(),
        "cert_exists": CERT_FILE.is_file(),
        "key_exists": KEY_FILE.is_file(),
        "cert_path": str(CERT_FILE),
        "key_path": str(KEY_FILE),
        "hostname": _hostname(),
    }


def generate(force: bool = False) -> None:
    if CERT_FILE.is_file() and KEY_FILE.is_file() and not force:
        return
    TLS_DIR.mkdir(parents=True, exist_ok=True)
    host = _hostname()
    sans = [f"DNS:{host}", f"DNS:{host}.local", "DNS:localhost", "IP:127.0.0.1"]
    for address in _ip_addresses():
        if address != "127.0.0.1":
            sans.append(f"IP:{address}")
    san_text = ",".join(sans)
    config = TLS_DIR / "openssl.cnf"
    config.write_text(
        "\n".join(
            [
                "[req]",
                "default_bits = 2048",
                "prompt = no",
                "default_md = sha256",
                "distinguished_name = dn",
                "x509_extensions = v3_req",
                "",
                "[dn]",
                "CN = MineBox",
                f"O = MineBox ({host})",
                "",
                "[v3_req]",
                "subjectAltName = " + san_text,
                "basicConstraints = CA:FALSE",
                "keyUsage = digitalSignature, keyEncipherment",
                "extendedKeyUsage = serverAuth",
                "",
            ]
        ),
        encoding="utf-8",
    )
    command = [
        "openssl",
        "req",
        "-x509",
        "-nodes",
        "-newkey",
        "rsa:2048",
        "-keyout",
        str(KEY_FILE),
        "-out",
        str(CERT_FILE),
        "-days",
        "825",
        "-config",
        str(config),
    ]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "openssl failed").strip()
        raise SystemExit(f"Could not generate TLS certificate: {detail}")
    try:
        os.chmod(KEY_FILE, 0o600)
        os.chmod(CERT_FILE, 0o644)
        # Allow minebox service user to read the key.
        subprocess.run(
            ["chown", "minebox:minebox", str(CERT_FILE), str(KEY_FILE)],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except OSError:
        pass


def enable() -> dict[str, object]:
    generate(force=False)
    ENABLED_FLAG.write_text("1\n", encoding="utf-8")
    try:
        os.chmod(ENABLED_FLAG, 0o644)
    except OSError:
        pass
    return status()


def disable() -> dict[str, object]:
    ENABLED_FLAG.unlink(missing_ok=True)
    return status()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("status", "generate", "enable", "disable"),
        help="TLS action",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate certificate even if one exists",
    )
    args = parser.parse_args()
    try:
        if args.action == "status":
            info = status()
            print(
                f"enabled={info['enabled']} cert={info['cert_exists']} "
                f"host={info['hostname']}"
            )
            return 0
        if args.action == "generate":
            generate(force=args.force)
            print(CERT_FILE)
            return 0
        if args.action == "enable":
            info = enable()
            print(f"enabled={info['enabled']}")
            return 0
        info = disable()
        print(f"enabled={info['enabled']}")
        return 0
    except SystemExit as error:
        message = error.args[0] if error.args else str(error)
        if message and message not in {"0", "1"}:
            print(message, file=sys.stderr)
        code = error.code
        return code if isinstance(code, int) else 1
    except Exception as error:  # noqa: BLE001
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
