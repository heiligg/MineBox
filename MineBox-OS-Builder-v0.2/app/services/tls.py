from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


TLS_DIR = Path("/var/lib/minebox/tls")
CERT_FILE = TLS_DIR / "cert.pem"
KEY_FILE = TLS_DIR / "key.pem"
ENABLED_FLAG = TLS_DIR / "enabled"
ENSURE_SCRIPT = Path("/opt/minebox/scripts/minebox_ensure_tls.py")


class TlsError(RuntimeError):
    pass


def is_enabled() -> bool:
    if os.environ.get("MINEBOX_TLS", "").strip() in {"1", "true", "yes", "on"}:
        return True
    return ENABLED_FLAG.is_file() and CERT_FILE.is_file() and KEY_FILE.is_file()


def status() -> dict[str, Any]:
    return {
        "enabled": is_enabled(),
        "cert_exists": CERT_FILE.is_file(),
        "key_exists": KEY_FILE.is_file(),
        "port": 8080,
        "scheme": "https" if is_enabled() else "http",
        "message": (
            "Dashboard HTTPS is on (self-signed). Browsers will warn until you trust the certificate."
            if is_enabled()
            else "Dashboard is serving plain HTTP on port 8080."
        ),
    }


def _run_ensure(action: str) -> None:
    helpers = [
        ["sudo", "-n", "/usr/bin/python3", str(ENSURE_SCRIPT), action],
        ["sudo", "-n", "/usr/local/sbin/minebox-ensure-tls", action],
        ["/usr/bin/python3", str(ENSURE_SCRIPT), action],
    ]
    errors: list[str] = []
    for command in helpers:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=90,
            )
        except (OSError, subprocess.SubprocessError) as error:
            errors.append(str(error))
            continue
        if result.returncode == 0:
            return
        detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
        errors.append(detail[:240])
    raise TlsError(
        "Could not update TLS. "
        + (errors[0] if errors else "ensure_tls helper missing.")
    )


def _restart_api() -> None:
    commands = [
        ["sudo", "-n", "/usr/bin/systemctl", "restart", "minebox-api.service"],
        ["systemctl", "restart", "minebox-api.service"],
    ]
    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return
    # Soft-fail: flag may still apply on next reboot/restart.
    return


def enable() -> dict[str, Any]:
    _run_ensure("enable")
    _restart_api()
    return {"ok": True, **status()}


def disable() -> dict[str, Any]:
    _run_ensure("disable")
    _restart_api()
    return {"ok": True, **status()}
