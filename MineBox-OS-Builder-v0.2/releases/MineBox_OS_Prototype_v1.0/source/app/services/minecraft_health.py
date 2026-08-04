"""Minecraft health probes — RUNNING requires evidence beyond PID."""

from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.secrets_store import redact_secrets
from core.states import HealthEvidence, is_healthy_running


@dataclass
class HealthCheckResult:
    healthy: bool
    evidence: HealthEvidence
    failed_checks: list[str] = field(default_factory=list)
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    recommended_action: str = ""
    phase: str = "unknown"  # starting | running | unhealthy | crashed | stopped

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "evidence": self.evidence.to_dict(),
            "failed_checks": list(self.failed_checks),
            "checked_at": self.checked_at,
            "recommended_action": self.recommended_action,
            "phase": self.phase,
        }


def _server_dir() -> Path | None:
    try:
        from services import servers

        active = servers.active_server()
        if active is None:
            return None
        return Path(active.directory)
    except Exception:
        return None


def _server_port() -> int:
    try:
        from services import servers

        active = servers.active_server()
        if active is not None:
            return int(active.port)
    except Exception:
        pass
    return 25565


def _rcon_port() -> int:
    try:
        from services import servers

        active = servers.active_server()
        if active is not None:
            return int(active.rcon_port)
    except Exception:
        pass
    return 25575


def port_listening(host: str = "127.0.0.1", port: int | None = None, timeout: float = 0.6) -> bool:
    port = _server_port() if port is None else port
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def rcon_responsive(timeout: float = 3.0) -> bool:
    try:
        from services import rcon

        if hasattr(rcon, "port_is_open") and not rcon.port_is_open():
            return False
        result = rcon.send("list", timeout=timeout)
        return bool(result.ok)
    except Exception:
        return False


def process_or_service_active() -> tuple[bool, bool]:
    """Return (process_present, service_active)."""
    try:
        from services import minecraft

        active = bool(minecraft.is_running())
        return active, active
    except Exception:
        return False, False


def recent_log_activity(max_age_s: float = 120.0) -> tuple[bool, str | None]:
    server_dir = _server_dir()
    if server_dir is None:
        return False, None
    log_path = server_dir / "logs" / "latest.log"
    if not log_path.is_file():
        return False, None
    try:
        mtime = log_path.stat().st_mtime
        age = time.time() - mtime
        if age <= max_age_s:
            return True, datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        return False, datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except OSError:
        return False, None


def startup_marker_present() -> bool:
    server_dir = _server_dir()
    if server_dir is None:
        return False
    log_path = server_dir / "logs" / "latest.log"
    if not log_path.is_file():
        return False
    try:
        # Read tail only.
        data = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    markers = ("Done (", "For help, type", "Timings Reset")
    return any(marker in data[-8000:] for marker in markers)


def collect_health(
    *,
    expect_starting: bool = False,
    rcon_enabled: bool = True,
) -> HealthCheckResult:
    process_present, service_active = process_or_service_active()
    listening = port_listening()
    rcon_ok = False
    if rcon_enabled and (process_present or service_active or listening):
        rcon_ok = rcon_responsive()
    log_ok, log_ts = recent_log_activity()
    started = startup_marker_present()

    evidence = HealthEvidence(
        process_present=process_present,
        service_active=service_active,
        port_listening=listening,
        rcon_responsive=rcon_ok,
        last_log_activity=log_ts,
        notes=[],
    )
    if started:
        evidence.notes.append("startup_marker_present")
    if expect_starting:
        evidence.notes.append("expect_starting")

    failed: list[str] = []
    if not process_present and not service_active:
        failed.append("process_or_service")
    if not listening:
        failed.append("server_port")
    if rcon_enabled and not rcon_ok:
        failed.append("rcon")
    if not log_ok and (process_present or service_active):
        failed.append("recent_log_activity")

    healthy = is_healthy_running(evidence)
    # Prefer RCON or port; startup marker can reinforce RUNNING while RCON flaky.
    if not healthy and (process_present or service_active) and listening and started:
        healthy = True
        evidence.notes.append("port_and_startup_marker_accepted")
        failed = [item for item in failed if item != "rcon"]

    if not process_present and not service_active and not listening:
        phase = "stopped"
        action = "Start the Minecraft server if players should connect."
    elif expect_starting and not healthy:
        phase = "starting"
        action = "Wait for startup timeout; server is not ready yet."
    elif healthy:
        phase = "running"
        action = "None"
    elif process_present or service_active:
        phase = "unhealthy"
        action = "Inspect logs; restart if the server is wedged."
    else:
        phase = "stopped"
        action = "Start the Minecraft server if needed."

    return HealthCheckResult(
        healthy=healthy,
        evidence=evidence,
        failed_checks=failed,
        recommended_action=action,
        phase=phase,
    )


def redact_health_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: redact_secrets(str(value)) if isinstance(value, str) else value for key, value in data.items()}
