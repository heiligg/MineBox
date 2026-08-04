"""Remote-access providers (Tailscale first). Disabled by default."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from core.secrets_store import redact_secrets

LOGGER = logging.getLogger("minebox.remote_access")


class ProviderState(str, Enum):
    NOT_INSTALLED = "NOT_INSTALLED"
    DISABLED = "DISABLED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RemoteAccessStatus:
    enabled: bool
    provider: str | None
    connected: bool
    state: str
    detail: str
    expose_dashboard: bool = False
    expose_minecraft: bool = False
    ipv4: str | None = None
    dns_name: str | None = None

    def to_public_dict(self, *, authenticated: bool = False) -> dict[str, Any]:
        data = {
            "enabled": self.enabled,
            "provider": self.provider,
            "connected": self.connected,
            "state": self.state,
            "detail": self.detail,
            "expose_dashboard": self.expose_dashboard,
            "expose_minecraft": self.expose_minecraft,
        }
        if authenticated:
            data["ipv4"] = self.ipv4
            data["dns_name"] = self.dns_name
        else:
            data["ipv4"] = None
            data["dns_name"] = None
        return data


@runtime_checkable
class RemoteAccessProvider(Protocol):
    name: str

    def status(self, *, authenticated: bool = False) -> RemoteAccessStatus: ...
    def enable(self, **kwargs: Any) -> RemoteAccessStatus: ...
    def disable(self, *, confirm: bool = False) -> RemoteAccessStatus: ...


def _runtime_dir() -> Path:
    return Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox"))


def remote_state_path() -> Path:
    override = os.environ.get("MINEBOX_REMOTE_ACCESS_FILE")
    if override:
        return Path(override)
    return _runtime_dir() / "remote_access.json"


def load_remote_state() -> dict[str, Any]:
    path = remote_state_path()
    if not path.is_file():
        return {
            "enabled": False,
            "provider": "tailscale",
            "expose_dashboard": False,
            "expose_minecraft": False,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_remote_state(data: dict[str, Any]) -> None:
    path = remote_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never persist auth keys.
    clean = {
        "enabled": bool(data.get("enabled")),
        "provider": data.get("provider") or "tailscale",
        "expose_dashboard": bool(data.get("expose_dashboard")),
        "expose_minecraft": bool(data.get("expose_minecraft")),
        "last_error": redact_secrets(str(data.get("last_error") or ""))[:500],
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


_AUTHKEY_RE = re.compile(r"^tskey-[a-z]+-[A-Za-z0-9_-]+$")


def validate_auth_key(auth_key: str) -> str:
    key = (auth_key or "").strip()
    if not key:
        raise ValueError("Auth key is required.")
    if len(key) > 200:
        raise ValueError("Auth key is too long.")
    if any(ch in key for ch in " \n\r\t;|&`$"):
        raise ValueError("Auth key contains invalid characters.")
    # Allow common Tailscale key shapes; do not require network validation here.
    if not (key.startswith("tskey-") or _AUTHKEY_RE.match(key)):
        # Still allow if it looks like a one-time key without leaking it.
        if len(key) < 20:
            raise ValueError("Auth key looks invalid.")
    return key


def _tailscale_bin() -> str | None:
    return shutil.which("tailscale")


def _run_tailscale(args: list[str], *, timeout: int = 45, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    binary = _tailscale_bin()
    if not binary:
        raise FileNotFoundError("tailscale not installed")
    # Strict argv only — never shell=True.
    return subprocess.run(
        [binary, *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_text,
    )


class NullRemoteAccessProvider:
    name = "none"

    def status(self, *, authenticated: bool = False) -> RemoteAccessStatus:
        return RemoteAccessStatus(
            enabled=False,
            provider=None,
            connected=False,
            state=ProviderState.DISABLED.value,
            detail="Remote access is disabled by default.",
        )

    def enable(self, **kwargs: Any) -> RemoteAccessStatus:
        _ = kwargs
        return self.status()

    def disable(self, *, confirm: bool = False) -> RemoteAccessStatus:
        _ = confirm
        return self.status()


class TailscaleRemoteAccessProvider:
    name = "tailscale"

    def status(self, *, authenticated: bool = False) -> RemoteAccessStatus:
        state = load_remote_state()
        enabled = bool(state.get("enabled"))
        expose_dashboard = bool(state.get("expose_dashboard"))
        expose_minecraft = bool(state.get("expose_minecraft"))

        if _tailscale_bin() is None:
            return RemoteAccessStatus(
                enabled=enabled,
                provider=self.name,
                connected=False,
                state=ProviderState.NOT_INSTALLED.value,
                detail="Tailscale is not installed on this appliance.",
                expose_dashboard=expose_dashboard,
                expose_minecraft=expose_minecraft,
            )

        if not enabled:
            return RemoteAccessStatus(
                enabled=False,
                provider=self.name,
                connected=False,
                state=ProviderState.DISABLED.value,
                detail="Tailscale remote access is disabled.",
                expose_dashboard=False,
                expose_minecraft=False,
            )

        ipv4 = None
        dns_name = None
        try:
            result = _run_tailscale(["status", "--json"], timeout=20)
            if result.returncode != 0:
                detail = redact_secrets(result.stderr or result.stdout or "tailscale status failed")
                return RemoteAccessStatus(
                    enabled=True,
                    provider=self.name,
                    connected=False,
                    state=ProviderState.ERROR.value,
                    detail=detail[:300],
                    expose_dashboard=expose_dashboard,
                    expose_minecraft=expose_minecraft,
                )
            payload = json.loads(result.stdout or "{}")
            backend = str(payload.get("BackendState") or "")
            self_node = payload.get("Self") or {}
            addrs = self_node.get("TailscaleIPs") or []
            if addrs:
                ipv4 = next((a for a in addrs if ":" not in a), addrs[0])
            dns_name = self_node.get("DNSName") or None
            if backend == "Running":
                st = ProviderState.CONNECTED
                detail = "Tailscale connected."
                connected = True
            elif backend in {"NeedsLogin", "NeedsMachineAuth"}:
                st = ProviderState.AUTH_REQUIRED
                detail = "Tailscale authentication required."
                connected = False
            elif backend in {"Starting", "Stopped"}:
                st = ProviderState.CONNECTING
                detail = f"Tailscale state: {backend}"
                connected = False
            else:
                st = ProviderState.DEGRADED
                detail = f"Tailscale state: {backend or 'unknown'}"
                connected = False
            status = RemoteAccessStatus(
                enabled=True,
                provider=self.name,
                connected=connected,
                state=st.value,
                detail=detail,
                expose_dashboard=expose_dashboard,
                expose_minecraft=expose_minecraft,
                ipv4=ipv4,
                dns_name=dns_name.rstrip(".") if isinstance(dns_name, str) else None,
            )
            return status
        except FileNotFoundError:
            return RemoteAccessStatus(
                enabled=enabled,
                provider=self.name,
                connected=False,
                state=ProviderState.NOT_INSTALLED.value,
                detail="Tailscale is not installed.",
                expose_dashboard=expose_dashboard,
                expose_minecraft=expose_minecraft,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("tailscale status error: %s", redact_secrets(str(exc)))
            return RemoteAccessStatus(
                enabled=True,
                provider=self.name,
                connected=False,
                state=ProviderState.ERROR.value,
                detail="Unable to read Tailscale status.",
                expose_dashboard=expose_dashboard,
                expose_minecraft=expose_minecraft,
            )

    def enable(self, **kwargs: Any) -> RemoteAccessStatus:
        auth_key = kwargs.get("auth_key") or kwargs.get("authkey") or ""
        expose_dashboard = bool(kwargs.get("expose_dashboard", False))
        expose_minecraft = bool(kwargs.get("expose_minecraft", False))

        if _tailscale_bin() is None:
            save_remote_state(
                {
                    "enabled": False,
                    "provider": self.name,
                    "expose_dashboard": False,
                    "expose_minecraft": False,
                    "last_error": "not_installed",
                }
            )
            return self.status(authenticated=True)

        try:
            key = validate_auth_key(str(auth_key))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        # Never log the key.
        LOGGER.info("tailscale_enable requested expose_dashboard=%s expose_minecraft=%s", expose_dashboard, expose_minecraft)
        try:
            result = _run_tailscale(
                ["up", f"--auth-key={key}", "--accept-dns=false"],
                timeout=90,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("tailscale up failed: %s", type(exc).__name__)
            save_remote_state(
                {
                    "enabled": False,
                    "provider": self.name,
                    "expose_dashboard": False,
                    "expose_minecraft": False,
                    "last_error": "up_failed",
                }
            )
            raise ValueError("Tailscale enable failed.") from exc

        if result.returncode != 0:
            LOGGER.warning("tailscale up exit=%s", result.returncode)
            save_remote_state(
                {
                    "enabled": False,
                    "provider": self.name,
                    "expose_dashboard": False,
                    "expose_minecraft": False,
                    "last_error": "up_nonzero",
                }
            )
            raise ValueError("Tailscale authentication failed.")

        save_remote_state(
            {
                "enabled": True,
                "provider": self.name,
                "expose_dashboard": expose_dashboard,
                "expose_minecraft": expose_minecraft,
            }
        )
        return self.status(authenticated=True)

    def disable(self, *, confirm: bool = False) -> RemoteAccessStatus:
        if not confirm:
            raise ValueError("Disabling remote access requires confirm=true.")
        LOGGER.info("tailscale_disable requested")
        if _tailscale_bin():
            try:
                _run_tailscale(["down"], timeout=30)
            except Exception:
                pass
        save_remote_state(
            {
                "enabled": False,
                "provider": self.name,
                "expose_dashboard": False,
                "expose_minecraft": False,
            }
        )
        return self.status(authenticated=True)

    def set_exposure(
        self,
        *,
        expose_dashboard: bool | None = None,
        expose_minecraft: bool | None = None,
    ) -> RemoteAccessStatus:
        state = load_remote_state()
        if not state.get("enabled"):
            raise ValueError("Enable Tailscale before changing exposure.")
        if expose_dashboard is not None:
            state["expose_dashboard"] = bool(expose_dashboard)
        if expose_minecraft is not None:
            state["expose_minecraft"] = bool(expose_minecraft)
        save_remote_state(state)
        LOGGER.info(
            "tailscale_exposure dashboard=%s minecraft=%s",
            state.get("expose_dashboard"),
            state.get("expose_minecraft"),
        )
        return self.status(authenticated=True)

    def logout(self, *, confirm: bool = False) -> RemoteAccessStatus:
        if not confirm:
            raise ValueError("Tailscale logout requires confirm=true.")
        if _tailscale_bin():
            try:
                _run_tailscale(["logout"], timeout=30)
            except Exception:
                pass
        return self.disable(confirm=True)


def get_remote_access_provider() -> RemoteAccessProvider:
    # Always Tailscale provider object; it reports DISABLED until enabled.
    return TailscaleRemoteAccessProvider()
