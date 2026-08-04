"""Coordinate hotspot PSK, RCON, and OS password rotation."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core import secrets_store
from core.bootstrap import mark_credential_rotated

LOGGER = logging.getLogger("minebox.secret_rotation")

HOTSPOT_SSID_RE = re.compile(r"^[\w ._-]{1,32}$")
# WPA-PSK: 8–63 ASCII
HOTSPOT_PSK_RE = re.compile(r"^[\x20-\x7e]{8,63}$")


class RotationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def validate_hotspot_ssid(ssid: str) -> str:
    ssid = (ssid or "").strip()
    if not HOTSPOT_SSID_RE.fullmatch(ssid):
        raise RotationError(
            "Hotspot SSID must be 1–32 characters (letters, numbers, space, . _ -)."
        )
    return ssid


def validate_hotspot_psk(psk: str) -> str:
    if secrets_store.is_bootstrap_hotspot_psk(psk):
        raise RotationError("Choose a new hotspot password (not the bootstrap default).")
    if not HOTSPOT_PSK_RE.fullmatch(psk or ""):
        raise RotationError("Hotspot password must be 8–63 ASCII characters.")
    return psk


def _hostapd_paths() -> list[Path]:
    return [
        Path("/etc/hostapd/hostapd.conf"),
        Path("/opt/minebox/services/hotspot/hostapd.conf"),
    ]


def rotate_hotspot_psk(ssid: str | None, psk: str) -> dict[str, Any]:
    ssid_value = validate_hotspot_ssid(ssid) if ssid else None
    psk_value = validate_hotspot_psk(psk)

    # Persist to secrets store first.
    secrets_path = Path(
        os.environ.get("MINEBOX_SECRETS_FILE", "/etc/minebox/secrets.env")
    )
    runtime_secrets = Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox")) / "secrets.env"
    values = {}
    for candidate in (secrets_path, runtime_secrets):
        if candidate.is_file():
            try:
                values.update(secrets_store.parse_env_file(candidate))
            except Exception:
                pass
    values["HOTSPOT_PSK"] = psk_value
    target = secrets_path if os.name != "nt" else runtime_secrets
    try:
        secrets_store.write_secrets_file(target, values)
    except OSError as exc:
        # Dev/CI fallback.
        try:
            secrets_store.write_secrets_file(runtime_secrets, values)
            target = runtime_secrets
        except OSError as exc2:
            raise RotationError(f"Could not write secrets file: {exc2}") from exc

    updated_files: list[str] = [str(target)]
    for path in _hostapd_paths():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
            lines = []
            saw_psk = False
            saw_ssid = False
            for line in text.splitlines():
                if line.startswith("wpa_passphrase="):
                    lines.append(f"wpa_passphrase={psk_value}")
                    saw_psk = True
                elif ssid_value and line.startswith("ssid="):
                    lines.append(f"ssid={ssid_value}")
                    saw_ssid = True
                else:
                    lines.append(line)
            if not saw_psk:
                lines.append(f"wpa_passphrase={psk_value}")
            if ssid_value and not saw_ssid:
                lines.append(f"ssid={ssid_value}")
            tmp = path.with_suffix(".tmp")
            tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
            tmp.replace(path)
            updated_files.append(str(path))
        except OSError as exc:
            LOGGER.warning("Could not update %s: %s", path, exc)

    # Best-effort hostapd restart (may fail in CI).
    restarted = False
    try:
        result = subprocess.run(
            ["sudo", "-n", "/usr/bin/systemctl", "restart", "hostapd.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        restarted = result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        restarted = False

    mark_credential_rotated("hotspot_psk")
    LOGGER.info("Hotspot PSK rotated (hostapd_restarted=%s)", restarted)
    return {
        "ok": True,
        "updated_files": updated_files,
        "hostapd_restarted": restarted,
        "ssid": ssid_value,
    }


def rotate_rcon_password() -> dict[str, Any]:
    from services import servers
    from core.secrets_store import get_or_create_server_rcon_password, generate_rcon_password
    from services import rcon as rcon_service

    active = servers.active_server()
    if active is None:
        # Still rotate shared fallback secret for future servers.
        password = generate_rcon_password()
        runtime = Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox")) / "secrets.env"
        values = {}
        if runtime.is_file():
            try:
                values = secrets_store.parse_env_file(runtime)
            except Exception:
                values = {}
        values["RCON_PASSWORD"] = password
        secrets_store.write_secrets_file(runtime, values)
        mark_credential_rotated("rcon_password")
        return {"ok": True, "servers_updated": 0, "message": "Stored new RCON secret for future servers."}

    # Force new password even if legacy file exists.
    server_dir = Path(active.directory)
    password_file = server_dir / ".minebox-rcon-password"
    password = generate_rcon_password()
    password_file.write_text(password + "\n", encoding="utf-8")
    try:
        password_file.chmod(0o600)
    except OSError:
        pass
    rcon_service.ensure_properties(server_dir)
    # ensure_properties may keep old if file existed — rewrite properties password.
    props_path = server_dir / "server.properties"
    if props_path.is_file():
        try:
            lines = []
            for line in props_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("rcon.password="):
                    lines.append(f"rcon.password={password}")
                else:
                    lines.append(line)
            props_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            raise RotationError(f"Could not update server.properties: {exc}") from exc

    mark_credential_rotated("rcon_password")
    LOGGER.info("RCON password rotated for server_id=%s", active.server_id)
    return {
        "ok": True,
        "servers_updated": 1,
        "server_id": active.server_id,
        "message": "RCON password rotated. Restart Minecraft if it was already running.",
    }


def rotate_os_password(new_password: str) -> dict[str, Any]:
    """Rotate the minebox OS account via a narrowly scoped helper."""
    from services import auth as auth_service

    auth_service.validate_password(new_password)
    helper = Path("/opt/minebox/scripts/minebox_set_os_password.py")
    if os.name == "nt" or not helper.is_file():
        # Documented deferred path for CI / incomplete images.
        mark_credential_rotated("os_account_password_deferred")
        _mark_os_deferred(True)
        return {
            "ok": True,
            "rotated": False,
            "deferred": True,
            "message": (
                "OS password helper unavailable in this environment. "
                "Password SSH will be disabled after setup when possible; "
                "rotate the minebox account from the local console."
            ),
        }

    try:
        result = subprocess.run(
            ["sudo", "-n", "/usr/bin/python3", str(helper), "minebox"],
            input=new_password + "\n",
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RotationError(f"OS password helper failed: {exc}") from exc

    if result.returncode != 0:
        # Fall back to deferred + SSH hardening intent.
        _mark_os_deferred(True)
        mark_credential_rotated("os_account_password_deferred")
        return {
            "ok": True,
            "rotated": False,
            "deferred": True,
            "message": (
                "Could not rotate OS password automatically. "
                "Marked as deferred; disable password SSH after setup."
            ),
        }

    mark_credential_rotated("os_account_password")
    _mark_os_deferred(False)
    LOGGER.info("OS account password rotated for minebox")
    return {"ok": True, "rotated": True, "deferred": False, "message": "OS password rotated."}


def _mark_os_deferred(deferred: bool) -> None:
    from core.bootstrap import load_bootstrap_file, save_bootstrap_file

    data = load_bootstrap_file()
    data["os_password_rotated"] = not deferred
    data["os_password_deferred"] = deferred
    save_bootstrap_file(data)


def disable_password_ssh() -> dict[str, Any]:
    """Best-effort: disable PasswordAuthentication after setup."""
    conf = Path("/etc/ssh/sshd_config.d/50-minebox-security.conf")
    try:
        conf.parent.mkdir(parents=True, exist_ok=True)
        conf.write_text(
            "# Managed by MineBox first-boot\n"
            "PasswordAuthentication no\n"
            "KbdInteractiveAuthentication no\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["sudo", "-n", "/usr/bin/systemctl", "reload", "ssh"],
            check=False,
            capture_output=True,
            timeout=20,
        )
        return {"ok": True, "password_ssh_disabled": True}
    except OSError:
        return {
            "ok": False,
            "password_ssh_disabled": False,
            "message": "Could not write sshd drop-in (may require image sudoers update).",
        }
