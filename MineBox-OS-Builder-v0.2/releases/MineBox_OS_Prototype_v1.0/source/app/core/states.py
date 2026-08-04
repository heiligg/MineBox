"""Formal MineBox state models (Minecraft + system/network/hardware health)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MinecraftState(str, Enum):
    NOT_INSTALLED = "NOT_INSTALLED"
    INSTALLING = "INSTALLING"
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    BACKING_UP = "BACKING_UP"
    UPDATING = "UPDATING"
    ERROR = "ERROR"
    CRASHED = "CRASHED"


class SystemHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class NetworkHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    LOCAL_ONLY = "LOCAL_ONLY"
    ONLINE = "ONLINE"
    ERROR = "ERROR"


class FeatureStatus(str, Enum):
    OK = "OK"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNSUPPORTED = "UNSUPPORTED"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


# Valid directed transitions. Self-transitions allowed for refresh/idempotency.
_ALLOWED: dict[MinecraftState, set[MinecraftState]] = {
    MinecraftState.NOT_INSTALLED: {
        MinecraftState.NOT_INSTALLED,
        MinecraftState.INSTALLING,
        MinecraftState.ERROR,
    },
    MinecraftState.INSTALLING: {
        MinecraftState.INSTALLING,
        MinecraftState.STOPPED,
        MinecraftState.ERROR,
    },
    MinecraftState.STOPPED: {
        MinecraftState.STOPPED,
        MinecraftState.STARTING,
        MinecraftState.BACKING_UP,
        MinecraftState.UPDATING,
        MinecraftState.INSTALLING,
        MinecraftState.ERROR,
        MinecraftState.NOT_INSTALLED,
    },
    MinecraftState.STARTING: {
        MinecraftState.STARTING,
        MinecraftState.RUNNING,
        MinecraftState.STOPPED,
        MinecraftState.ERROR,
        MinecraftState.CRASHED,
    },
    MinecraftState.RUNNING: {
        MinecraftState.RUNNING,
        MinecraftState.STOPPING,
        MinecraftState.BACKING_UP,
        MinecraftState.UPDATING,
        MinecraftState.ERROR,
        MinecraftState.CRASHED,
    },
    MinecraftState.STOPPING: {
        MinecraftState.STOPPING,
        MinecraftState.STOPPED,
        MinecraftState.ERROR,
        MinecraftState.CRASHED,
    },
    MinecraftState.BACKING_UP: {
        MinecraftState.BACKING_UP,
        MinecraftState.RUNNING,
        MinecraftState.STOPPED,
        MinecraftState.ERROR,
    },
    MinecraftState.UPDATING: {
        MinecraftState.UPDATING,
        MinecraftState.STOPPED,
        MinecraftState.RUNNING,
        MinecraftState.ERROR,
    },
    MinecraftState.ERROR: {
        MinecraftState.ERROR,
        MinecraftState.STOPPED,
        MinecraftState.STARTING,
        MinecraftState.INSTALLING,
        MinecraftState.NOT_INSTALLED,
    },
    MinecraftState.CRASHED: {
        MinecraftState.CRASHED,
        MinecraftState.STOPPED,
        MinecraftState.STARTING,
        MinecraftState.ERROR,
    },
}


class InvalidTransition(Exception):
    def __init__(self, current: MinecraftState, target: MinecraftState) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Invalid Minecraft transition {current.value} → {target.value}")


def can_transition(current: MinecraftState, target: MinecraftState) -> bool:
    return target in _ALLOWED.get(current, set())


def validate_transition(current: MinecraftState, target: MinecraftState) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(current, target)


@dataclass
class HealthEvidence:
    process_present: bool = False
    service_active: bool = False
    port_listening: bool = False
    rcon_responsive: bool = False
    last_log_activity: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_present": self.process_present,
            "service_active": self.service_active,
            "port_listening": self.port_listening,
            "rcon_responsive": self.rcon_responsive,
            "last_log_activity": self.last_log_activity,
            "notes": list(self.notes),
        }


@dataclass
class MinecraftStateInfo:
    value: MinecraftState
    reason: str = ""
    since: datetime = field(default_factory=_utc_now)
    last_error: str | None = None
    health: HealthEvidence = field(default_factory=HealthEvidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value.value,
            "reason": self.reason,
            "since": self.since.isoformat(),
            "last_error": self.last_error,
            "health": self.health.to_dict(),
        }


@dataclass
class TransitionResult:
    ok: bool
    state: MinecraftStateInfo
    error: str | None = None


class MinecraftStateMachine:
    """In-memory Minecraft lifecycle state with transition validation."""

    def __init__(self, initial: MinecraftState = MinecraftState.NOT_INSTALLED) -> None:
        self._info = MinecraftStateInfo(value=initial, reason="initialized")

    @property
    def info(self) -> MinecraftStateInfo:
        return self._info

    @property
    def value(self) -> MinecraftState:
        return self._info.value

    def transition(
        self,
        target: MinecraftState,
        *,
        reason: str = "",
        last_error: str | None = None,
        health: HealthEvidence | None = None,
        force: bool = False,
    ) -> TransitionResult:
        if not force:
            try:
                validate_transition(self._info.value, target)
            except InvalidTransition as exc:
                return TransitionResult(ok=False, state=self._info, error=str(exc))

        same = target == self._info.value
        self._info = MinecraftStateInfo(
            value=target,
            reason=reason or self._info.reason,
            since=self._info.since if same else _utc_now(),
            last_error=last_error,
            health=health if health is not None else self._info.health,
        )
        return TransitionResult(ok=True, state=self._info)

    def refresh_health(self, health: HealthEvidence, *, reason: str = "") -> MinecraftStateInfo:
        """Update health evidence and optionally downgrade RUNNING if unhealthy."""
        current = self._info.value
        if current == MinecraftState.RUNNING and not is_healthy_running(health):
            self.transition(
                MinecraftState.ERROR,
                reason=reason or "Process present but server health checks failed",
                last_error="unhealthy_while_running",
                health=health,
            )
        else:
            self._info.health = health
            if reason:
                self._info.reason = reason
        return self._info


def is_healthy_running(health: HealthEvidence) -> bool:
    """RUNNING requires more than a PID/process presence alone."""
    if not (health.process_present or health.service_active):
        return False
    # Prefer RCON or listening port as positive evidence.
    return bool(health.rcon_responsive or health.port_listening)


def resolve_minecraft_state(
    *,
    installed: bool,
    installing: bool = False,
    backing_up: bool = False,
    updating: bool = False,
    stopping: bool = False,
    starting: bool = False,
    health: HealthEvidence | None = None,
    crashed: bool = False,
    error: str | None = None,
) -> MinecraftStateInfo:
    """Derive a state from operational flags + health evidence (no PID==RUNNING)."""
    health = health or HealthEvidence()
    if error and not any((installing, starting, stopping, backing_up, updating)):
        return MinecraftStateInfo(
            value=MinecraftState.ERROR,
            reason=error,
            last_error=error,
            health=health,
        )
    if not installed and not installing:
        return MinecraftStateInfo(
            value=MinecraftState.NOT_INSTALLED,
            reason="No Minecraft server installed",
            health=health,
        )
    if installing:
        return MinecraftStateInfo(value=MinecraftState.INSTALLING, reason="Installing", health=health)
    if updating:
        return MinecraftStateInfo(value=MinecraftState.UPDATING, reason="Updating", health=health)
    if backing_up:
        return MinecraftStateInfo(value=MinecraftState.BACKING_UP, reason="Backing up", health=health)
    if stopping:
        return MinecraftStateInfo(value=MinecraftState.STOPPING, reason="Stopping", health=health)
    if starting:
        return MinecraftStateInfo(value=MinecraftState.STARTING, reason="Starting", health=health)
    if crashed:
        return MinecraftStateInfo(
            value=MinecraftState.CRASHED,
            reason="Server crashed",
            last_error="crashed",
            health=health,
        )
    if is_healthy_running(health):
        return MinecraftStateInfo(
            value=MinecraftState.RUNNING,
            reason="Health checks passed",
            health=health,
        )
    if health.process_present or health.service_active:
        return MinecraftStateInfo(
            value=MinecraftState.ERROR,
            reason="Process/service present but not healthy (PID alone is not RUNNING)",
            last_error="unhealthy_process",
            health=health,
        )
    return MinecraftStateInfo(value=MinecraftState.STOPPED, reason="Server stopped", health=health)


@dataclass
class ComponentState:
    value: str
    reason: str = ""
    since: datetime = field(default_factory=_utc_now)
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "reason": self.reason,
            "since": self.since.isoformat(),
            "last_error": self.last_error,
        }
