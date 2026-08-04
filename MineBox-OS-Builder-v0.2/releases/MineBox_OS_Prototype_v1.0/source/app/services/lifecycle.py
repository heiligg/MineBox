"""Minecraft lifecycle manager integrated with the formal state machine."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.secrets_store import redact_secrets
from core.states import (
    HealthEvidence,
    MinecraftState,
    MinecraftStateMachine,
    resolve_minecraft_state,
)
from services.operations import OperationConflict, OperationType, get_coordinator
from services.system import CommandResult

LOGGER = logging.getLogger("minebox.lifecycle")


def _runtime_dir() -> Path:
    return Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox"))


def _state_path() -> Path:
    return _runtime_dir() / "minecraft_lifecycle.json"


class LifecycleError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class MinecraftLifecycleManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._machine = MinecraftStateMachine(MinecraftState.NOT_INSTALLED)
        self._last_error: str | None = None
        self._startup_timeout_s = float(os.environ.get("MINEBOX_MC_STARTUP_TIMEOUT", "180"))
        self._shutdown_timeout_s = float(os.environ.get("MINEBOX_MC_SHUTDOWN_TIMEOUT", "60"))
        self._load_persisted()
        self.refresh(reason="lifecycle_init")

    def _load_persisted(self) -> None:
        path = _state_path()
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        value = data.get("state")
        try:
            state = MinecraftState(value)
        except (TypeError, ValueError):
            return
        self._machine.transition(
            state,
            reason=str(data.get("reason") or "restored"),
            last_error=data.get("last_error"),
            force=True,
        )
        self._last_error = data.get("last_error")

    def _persist(self) -> None:
        path = _state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "state": self._machine.value.value,
                "reason": self._machine.info.reason,
                "last_error": self._machine.info.last_error,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            LOGGER.warning("Could not persist lifecycle state: %s", exc)

    def _installed(self) -> bool:
        try:
            from services import servers

            return bool(servers.list_servers())
        except Exception:
            return False

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            info = self._machine.info
            return {
                "state": info.to_dict(),
                "last_error": self._last_error,
                "startup_timeout_s": self._startup_timeout_s,
                "shutdown_timeout_s": self._shutdown_timeout_s,
            }

    def refresh(self, *, reason: str = "", expect_starting: bool = False) -> dict[str, Any]:
        from services import minecraft_health

        with self._lock:
            health = minecraft_health.collect_health(expect_starting=expect_starting)
            installed = self._installed()
            current = self._machine.value

            # Do not clobber transitional states mid-operation unless evidence demands it.
            if current in {
                MinecraftState.STARTING,
                MinecraftState.STOPPING,
                MinecraftState.BACKING_UP,
                MinecraftState.UPDATING,
                MinecraftState.INSTALLING,
            } and not expect_starting:
                if current is MinecraftState.STARTING and health.healthy:
                    self._machine.transition(
                        MinecraftState.RUNNING,
                        reason=reason or "health_ok",
                        health=health.evidence,
                    )
                elif current is MinecraftState.STARTING and not (
                    health.evidence.process_present or health.evidence.service_active
                ):
                    # Still within startup window handled by start().
                    self._machine.info.health = health.evidence
                else:
                    self._machine.info.health = health.evidence
                self._persist()
                return self.snapshot()

            derived = resolve_minecraft_state(
                installed=installed,
                health=health.evidence,
                error=self._last_error if health.phase == "unhealthy" else None,
            )
            # Preserve CRASHED until explicit recover if we already marked crash.
            if current is MinecraftState.CRASHED and derived.value in {
                MinecraftState.STOPPED,
                MinecraftState.ERROR,
            }:
                self._machine.info.health = health.evidence
                self._persist()
                return self.snapshot()

            self._machine.transition(
                derived.value,
                reason=reason or derived.reason,
                last_error=derived.last_error,
                health=health.evidence,
                force=True,
            )
            self._persist()
            return self.snapshot()

    def _require_transition(self, target: MinecraftState, *, reason: str) -> None:
        result = self._machine.transition(target, reason=reason)
        if not result.ok:
            raise LifecycleError(result.error or f"Invalid transition to {target.value}")
        self._persist()

    def start(self, *, coordinate: bool = True) -> CommandResult:
        from services import minecraft as mc
        from services import minecraft_health

        coordinator = get_coordinator()
        op = None
        if coordinate:
            try:
                op = coordinator.begin(OperationType.START, step="validate")
            except OperationConflict as exc:
                return CommandResult(False, stderr=str(exc))

        def _done(error: str | None = None) -> None:
            if op is not None:
                coordinator.complete(op.id, error=error)

        with self._lock:
            self.refresh(reason="pre_start")
            if self._machine.value is MinecraftState.RUNNING:
                _done()
                return CommandResult(True, "Minecraft is already running.")
            if self._machine.value is MinecraftState.STARTING:
                _done("already starting")
                return CommandResult(False, stderr="Minecraft is already starting.")
            if self._machine.value is MinecraftState.CRASHED:
                _done("crashed")
                return CommandResult(
                    False,
                    stderr=(
                        "Server is CRASHED. Call recover() or POST "
                        "/api/v1/minecraft/recover before starting."
                    ),
                )
            if not self._installed():
                self._machine.transition(
                    MinecraftState.NOT_INSTALLED, reason="no server", force=True
                )
                self._persist()
                _done("not installed")
                return CommandResult(False, stderr="No Minecraft server is installed.")

            try:
                self._require_transition(MinecraftState.STARTING, reason="user_start")
            except LifecycleError as exc:
                _done(str(exc))
                return CommandResult(False, stderr=str(exc))
            self._last_error = None

        if op is not None:
            coordinator.update(op.id, progress=0.2, step="service_start")
        result = mc.start_service()
        if not result.ok:
            with self._lock:
                self._last_error = redact_secrets(result.stderr or "start failed")
                self._machine.transition(
                    MinecraftState.CRASHED,
                    reason="start_failed",
                    last_error=self._last_error,
                    force=True,
                )
                self._persist()
            try:
                from services import crash_recovery

                crash_recovery.record_failure(self._last_error or "start_failed")
            except Exception:
                pass
            _done(self._last_error)
            return result

        if op is not None:
            coordinator.update(op.id, progress=0.5, step="wait_healthy")
        deadline = time.monotonic() + self._startup_timeout_s
        while time.monotonic() < deadline:
            health = minecraft_health.collect_health(expect_starting=True)
            if health.healthy:
                with self._lock:
                    self._machine.transition(
                        MinecraftState.RUNNING,
                        reason="health_ok",
                        health=health.evidence,
                        force=True,
                    )
                    self._persist()
                _done()
                return CommandResult(True, result.stdout or "Minecraft is running.")
            if not (health.evidence.process_present or health.evidence.service_active):
                # Allow a short settle window, then treat as crash/timeout.
                if time.monotonic() > (deadline - self._startup_timeout_s + 10):
                    break
            time.sleep(2)

        with self._lock:
            self._last_error = "Startup timeout or process exited before healthy"
            self._machine.transition(
                MinecraftState.CRASHED,
                reason=self._last_error,
                last_error=self._last_error,
                force=True,
            )
            self._persist()
        try:
            from services import crash_recovery

            crash_recovery.record_failure(self._last_error)
        except Exception:
            pass
        _done(self._last_error)
        return CommandResult(False, stderr=self._last_error)

    def stop(self, *, coordinate: bool = True) -> CommandResult:
        from services import minecraft as mc

        coordinator = get_coordinator()
        op = None
        if coordinate:
            try:
                op = coordinator.begin(OperationType.STOP, step="stopping")
            except OperationConflict as exc:
                return CommandResult(False, stderr=str(exc))

        def _done(error: str | None = None) -> None:
            if op is not None:
                coordinator.complete(op.id, error=error)

        with self._lock:
            self.refresh(reason="pre_stop")
            if self._machine.value in {
                MinecraftState.STOPPED,
                MinecraftState.NOT_INSTALLED,
            }:
                _done()
                return CommandResult(True, "Minecraft is already offline.")
            self._machine.transition(
                MinecraftState.STOPPING, reason="user_stop", force=True
            )
            self._persist()

        service_result = mc.stop_service()
        if not service_result.ok:
            with self._lock:
                self._last_error = redact_secrets(service_result.stderr or "stop failed")
                self._machine.transition(
                    MinecraftState.ERROR,
                    reason="stop_failed",
                    last_error=self._last_error,
                    force=True,
                )
                self._persist()
            _done(self._last_error)
            return service_result

        deadline = time.monotonic() + self._shutdown_timeout_s
        while time.monotonic() < deadline:
            if not mc.is_running():
                break
            time.sleep(0.5)

        with self._lock:
            if mc.is_running():
                self._last_error = "Stop timeout"
                self._machine.transition(
                    MinecraftState.ERROR,
                    reason="stop_timeout",
                    last_error=self._last_error,
                    force=True,
                )
                self._persist()
                _done(self._last_error)
                return CommandResult(False, stderr=self._last_error)
            self._machine.transition(
                MinecraftState.STOPPED, reason="stopped", force=True
            )
            self._persist()
        _done()
        return CommandResult(True, service_result.stdout or "Minecraft stopped.")

    def restart(self) -> CommandResult:
        coordinator = get_coordinator()
        try:
            op = coordinator.begin(OperationType.RESTART, step="restart")
        except OperationConflict as exc:
            return CommandResult(False, stderr=str(exc))
        stopped = self.stop(coordinate=False)
        if not stopped.ok and "already offline" not in (stopped.stdout or "").lower():
            if stopped.stderr:
                coordinator.complete(op.id, error=stopped.stderr)
                return stopped
        started = self.start(coordinate=False)
        coordinator.complete(op.id, error=None if started.ok else started.stderr)
        return started

    def recover(self) -> CommandResult:
        """Explicit recovery from CRASHED → allow start."""
        coordinator = get_coordinator()
        try:
            op = coordinator.begin(OperationType.RECOVER, step="recover")
        except OperationConflict as exc:
            return CommandResult(False, stderr=str(exc))
        with self._lock:
            if self._machine.value not in {
                MinecraftState.CRASHED,
                MinecraftState.ERROR,
            }:
                coordinator.complete(op.id)
                return CommandResult(True, f"Nothing to recover ({self._machine.value.value}).")
            self._machine.transition(
                MinecraftState.STOPPED,
                reason="explicit_recover",
                force=True,
            )
            self._last_error = None
            self._persist()
        try:
            from services import crash_recovery

            crash_recovery.reset_attempts()
        except Exception:
            pass
        started = self.start(coordinate=False)
        coordinator.complete(op.id, error=None if started.ok else started.stderr)
        return started

    def begin_backup_state(self) -> None:
        with self._lock:
            current = self._machine.value
            if current is MinecraftState.RUNNING:
                result = self._machine.transition(
                    MinecraftState.BACKING_UP, reason="backup"
                )
            elif current is MinecraftState.STOPPED:
                result = self._machine.transition(
                    MinecraftState.BACKING_UP, reason="backup"
                )
            else:
                raise LifecycleError(
                    f"Cannot backup from state {current.value}."
                )
            if not result.ok:
                raise LifecycleError(result.error or "Invalid backup transition")
            self._persist()

    def end_backup_state(self, *, was_running: bool, error: str | None = None) -> None:
        with self._lock:
            if error:
                self._last_error = redact_secrets(error)
                self._machine.transition(
                    MinecraftState.ERROR if was_running else MinecraftState.STOPPED,
                    reason="backup_failed",
                    last_error=self._last_error,
                    force=True,
                )
            else:
                target = MinecraftState.RUNNING if was_running else MinecraftState.STOPPED
                self._machine.transition(target, reason="backup_complete", force=True)
            self._persist()

    def mark_crashed(self, reason: str) -> None:
        with self._lock:
            self._last_error = redact_secrets(reason)
            self._machine.transition(
                MinecraftState.CRASHED,
                reason=self._last_error,
                last_error=self._last_error,
                force=True,
            )
            self._persist()


_manager: MinecraftLifecycleManager | None = None


def get_lifecycle() -> MinecraftLifecycleManager:
    global _manager
    if _manager is None:
        _manager = MinecraftLifecycleManager()
    return _manager


def reset_lifecycle() -> None:
    global _manager
    _manager = None
