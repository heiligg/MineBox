"""Shared backend state foundation for web and display UIs."""

from __future__ import annotations

import os
from typing import Any

from core import bootstrap
from core.minebox_config import ConfigError, get_config
from core.secrets_store import redact_secrets
from core.states import (
    HealthEvidence,
    MinecraftStateMachine,
    resolve_minecraft_state,
)
from hardware.factory import get_hardware


class StateService:
    def __init__(self) -> None:
        self.minecraft_sm = MinecraftStateMachine()

    def app_version(self) -> str:
        try:
            from config import APP_VERSION

            return str(APP_VERSION)
        except Exception:  # noqa: BLE001
            return "unknown"

    def setup_state(self) -> dict[str, Any]:
        return bootstrap.get_bootstrap_state().to_public_dict()

    def config_summary(self) -> dict[str, Any]:
        try:
            cfg = get_config()
        except ConfigError as exc:
            return {
                "ok": False,
                "error": str(exc),
            }
        return {
            "ok": True,
            "device_name": cfg.device_name,
            "api_bind": cfg.api_bind,
            "api_port": cfg.api_port,
            "dashboard_port": cfg.dashboard_port,
            "minecraft_data_path": cfg.minecraft_data_path,
            "supported_providers": list(cfg.supported_providers),
            "experimental_providers": list(cfg.experimental_providers),
            "hotspot_ssid": cfg.hotspot_ssid,
            "hotspot_subnet": cfg.hotspot_subnet,
            "internet_sharing": cfg.internet_sharing,
            "display_mode": cfg.display_mode,
            "display_resolution": {
                "width": cfg.display_width,
                "height": cfg.display_height,
            },
            "hardware_profile": cfg.hardware_profile,
            "update_channel": cfg.update_channel,
            "logging_level": cfg.logging_level,
            "source_path": cfg.source_path,
            "hardware_source_path": cfg.hardware_source_path,
        }

    def provider_capabilities(self) -> list[dict[str, Any]]:
        try:
            from services import servers

            return servers.provider_capabilities()
        except Exception:  # noqa: BLE001
            cfg = get_config()
            rows = []
            for name in cfg.supported_providers:
                rows.append({"id": name, "status": "supported", "v1_official": True})
            for name in cfg.experimental_providers:
                rows.append({"id": name, "status": "experimental", "v1_official": False})
            return rows

    def minecraft_state(self) -> dict[str, Any]:
        try:
            from services.lifecycle import get_lifecycle

            snap = get_lifecycle().refresh(reason="status_poll")
            state = dict(snap.get("state") or {})
            try:
                from services import minecraft, minecraft_health

                health = minecraft_health.collect_health()
                state["health_check"] = health.to_dict()
                state["legacy_running"] = bool(minecraft.is_running())
                state["version"] = minecraft.version()
                state["players"] = minecraft.player_count_text()
            except Exception as exc:  # noqa: BLE001
                state["health_check_error"] = redact_secrets(str(exc))
            return state
        except Exception as exc:  # noqa: BLE001
            installed = False
            health = HealthEvidence()
            try:
                from services import servers

                installed = bool(servers.list_servers())
            except Exception:
                pass
            info = resolve_minecraft_state(installed=installed, health=health)
            payload = info.to_dict()
            payload["error"] = redact_secrets(str(exc))
            return payload

    def system_health(self) -> dict[str, Any]:
        thermal: dict[str, Any] = {}
        try:
            from services import thermal as thermal_service

            thermal = thermal_service.update()
        except Exception as exc:  # noqa: BLE001
            thermal = {"error": redact_secrets(str(exc))}

        metrics: dict[str, Any] = {}
        try:
            from services import monitoring

            # Prefer existing monitoring helpers without inventing GPIO fan control.
            metrics = {
                "cpu_percent": getattr(monitoring, "sample", lambda: None)(),
            }
            sample = monitoring.sample()
            metrics = {
                "cpu_percent": sample.cpu,
                "memory_percent": sample.memory,
                "server_memory_mb": sample.server_memory_mb,
            }
            if hasattr(monitoring, "system_status"):
                status = monitoring.system_status()
                if isinstance(status, dict):
                    metrics.update(
                        {
                            "disk_percent": status.get("disk_percent")
                            or status.get("disk"),
                            "uptime": status.get("uptime"),
                            "hostname": status.get("hostname"),
                            "ip_address": status.get("ip_address") or status.get("ip"),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            metrics["error"] = redact_secrets(str(exc))

        temp_c = thermal.get("temperature_c")
        thermal_state = str(thermal.get("state") or "UNKNOWN")
        value = "HEALTHY"
        reason = "OK"
        if thermal_state == "SENSOR_UNAVAILABLE":
            value = "UNKNOWN"
            reason = "Temperature sensor unavailable"
        elif thermal_state == "CRITICAL":
            value = "CRITICAL"
            reason = "CPU temperature critical"
        elif thermal_state in {"HOT", "WARM"}:
            value = "DEGRADED"
            reason = f"Thermal state {thermal_state}"

        return {
            "value": value,
            "reason": reason,
            "temperature_c": temp_c,
            "fan": thermal.get("fan_state"),
            "fan_capability": thermal.get("fan_capability"),
            "throttling": thermal.get("throttling"),
            "thermal": thermal,
            "metrics": metrics,
        }

    def hardware_status(self) -> dict[str, Any]:
        hw = get_hardware()
        health = hw.health()
        return {
            "profile": hw.profile_name,
            "capabilities": hw.capabilities(),
            "health": health.to_dict(),
            "gpio_verification": health.gpio_verification,
            "unresolved_features": [
                name
                for name, status in hw.capabilities().items()
                if status in {"NOT_CONFIGURED", "UNSUPPORTED"}
            ],
            "diagnostic": hw.diagnostic_snapshot(),
        }

    def network_summary(self) -> dict[str, Any]:
        """Central network snapshot (no secrets)."""
        try:
            from networking.state import snapshot

            return snapshot(authenticated=False, include_legacy=False)
        except Exception as exc:  # noqa: BLE001
            try:
                cfg = get_config()
                return {
                    "hotspot_ssid": cfg.hotspot_ssid,
                    "hotspot_address": cfg.hotspot_address,
                    "error": redact_secrets(str(exc)),
                }
            except ConfigError as cfg_exc:
                return {"error": str(cfg_exc)}

    # Backward-compatible alias
    network_summary_placeholder = network_summary

    def _remote_access_public(self) -> dict[str, Any]:
        try:
            from networking.remote_access import get_remote_access_provider

            return get_remote_access_provider().status(authenticated=False).to_public_dict(
                authenticated=False
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "enabled": False,
                "provider": "tailscale",
                "state": "DISABLED",
                "detail": redact_secrets(str(exc)),
            }

    def public_status(self) -> dict[str, Any]:
        """Aggregate read-only status with secrets excluded."""
        ops: list[dict[str, Any]] = []
        crash: dict[str, Any] = {}
        backups: dict[str, Any] = {}
        try:
            from services.operations import get_coordinator

            ops = get_coordinator().current()
        except Exception:
            pass
        try:
            from services import crash_recovery

            crash = crash_recovery.status()
        except Exception as exc:  # noqa: BLE001
            crash = {"error": redact_secrets(str(exc))}
        try:
            from services import backups as backup_service

            status = backup_service.backup_status()
            backups = {
                "backup_count": status.get("backup_count"),
                "busy": status.get("busy"),
                "retention": status.get("retention"),
                "automatic_backup_hours": status.get("automatic_backup_hours"),
            }
        except Exception as exc:  # noqa: BLE001
            backups = {"error": redact_secrets(str(exc))}

        payload = {
            "ok": True,
            "version": self.app_version(),
            "setup": self.setup_state(),
            "config": self.config_summary(),
            "minecraft": self.minecraft_state(),
            "system": self.system_health(),
            "hardware": self.hardware_status(),
            "providers": self.provider_capabilities(),
            "network": self.network_summary(),
            "operations": ops,
            "crash_history": crash,
            "backups": backups,
            "remote_access": self._remote_access_public(),
        }
        # Defense in depth: redact any accidental secret leakage.
        return _redact_tree(payload)


def _redact_tree(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [_redact_tree(v) for v in value]
    if isinstance(value, dict):
        banned = {
            "password",
            "psk",
            "secret",
            "token",
            "authkey",
            "rcon_password",
            "session_secret",
            "hotspot_psk",
        }
        out = {}
        for key, item in value.items():
            if str(key).lower() in banned or str(key).lower().endswith("_password"):
                out[key] = "[REDACTED]"
            else:
                out[key] = _redact_tree(item)
        return out
    return value


_service: StateService | None = None


def _is_raspberry_pi_host() -> bool:
    return os.path.exists("/sys/firmware/devicetree/base/model") or os.path.exists(
        "/proc/device-tree/model"
    )


def get_state_service() -> StateService:
    global _service
    if _service is None:
        # Prefer mock hardware in non-appliance environments.
        if os.environ.get("MINEBOX_HARDWARE_PROFILE", "").strip() == "" and not _is_raspberry_pi_host():
            os.environ.setdefault("MINEBOX_FORCE_MOCK_HARDWARE", "1")
        _service = StateService()
    return _service


def reset_state_service() -> None:
    global _service
    _service = None
