"""Long-running operation coordinator and conflict locks."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class OperationType(str, Enum):
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    BACKUP = "backup"
    RESTORE = "restore"
    UPDATE = "update"
    SHUTDOWN = "shutdown"
    RECOVER = "recover"


class OperationState(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Operation:
    id: str
    type: OperationType
    state: OperationState
    progress: float
    step: str
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.id,
            "type": self.type.value,
            "state": self.state.value,
            "progress": self.progress,
            "current_step": self.step,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "meta": dict(self.meta),
        }


_CONFLICTS: dict[OperationType, set[OperationType]] = {
    OperationType.START: {
        OperationType.START,
        OperationType.STOP,
        OperationType.RESTART,
        OperationType.RESTORE,
        OperationType.UPDATE,
        OperationType.SHUTDOWN,
    },
    OperationType.STOP: {
        OperationType.START,
        OperationType.STOP,
        OperationType.RESTART,
        OperationType.BACKUP,
        OperationType.RESTORE,
        OperationType.UPDATE,
    },
    OperationType.RESTART: {
        OperationType.START,
        OperationType.STOP,
        OperationType.RESTART,
        OperationType.BACKUP,
        OperationType.RESTORE,
        OperationType.UPDATE,
        OperationType.SHUTDOWN,
    },
    OperationType.BACKUP: {
        OperationType.BACKUP,
        OperationType.RESTORE,
        OperationType.UPDATE,
        OperationType.START,
        OperationType.STOP,
        OperationType.RESTART,
        OperationType.SHUTDOWN,
    },
    OperationType.RESTORE: {
        OperationType.BACKUP,
        OperationType.RESTORE,
        OperationType.UPDATE,
        OperationType.START,
        OperationType.STOP,
        OperationType.RESTART,
        OperationType.SHUTDOWN,
    },
    OperationType.UPDATE: {
        OperationType.BACKUP,
        OperationType.RESTORE,
        OperationType.UPDATE,
        OperationType.START,
        OperationType.RESTART,
        OperationType.SHUTDOWN,
    },
    OperationType.SHUTDOWN: {
        OperationType.START,
        OperationType.RESTART,
        OperationType.BACKUP,
        OperationType.RESTORE,
        OperationType.UPDATE,
        OperationType.SHUTDOWN,
    },
    OperationType.RECOVER: {
        OperationType.START,
        OperationType.RECOVER,
        OperationType.RESTORE,
        OperationType.UPDATE,
        OperationType.SHUTDOWN,
    },
}


class OperationConflict(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class OperationCoordinator:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active: dict[str, Operation] = {}
        self._history: list[Operation] = []

    def begin(self, op_type: OperationType, *, step: str = "starting", meta: dict | None = None) -> Operation:
        with self._lock:
            for existing in self._active.values():
                if existing.state is not OperationState.RUNNING:
                    continue
                blocked = _CONFLICTS.get(op_type, set())
                if existing.type in blocked or op_type in _CONFLICTS.get(existing.type, set()):
                    raise OperationConflict(
                        f"Cannot start {op_type.value}: conflicts with active "
                        f"{existing.type.value} ({existing.id})."
                    )
            op = Operation(
                id=uuid.uuid4().hex[:12],
                type=op_type,
                state=OperationState.RUNNING,
                progress=0.0,
                step=step,
                started_at=datetime.now(timezone.utc).isoformat(),
                meta=dict(meta or {}),
            )
            self._active[op.id] = op
            return op

    def update(self, op_id: str, *, progress: float | None = None, step: str | None = None) -> None:
        with self._lock:
            op = self._active.get(op_id)
            if op is None:
                return
            if progress is not None:
                op.progress = max(0.0, min(1.0, float(progress)))
            if step is not None:
                op.step = step

    def complete(self, op_id: str, *, error: str | None = None) -> Operation | None:
        with self._lock:
            op = self._active.pop(op_id, None)
            if op is None:
                return None
            op.finished_at = datetime.now(timezone.utc).isoformat()
            op.progress = 1.0 if error is None else op.progress
            op.state = OperationState.FAILED if error else OperationState.COMPLETED
            op.error = error
            self._history.append(op)
            self._history = self._history[-50:]
            return op

    def current(self) -> list[dict[str, Any]]:
        with self._lock:
            return [op.to_dict() for op in self._active.values()]

    def history(self) -> list[dict[str, Any]]:
        with self._lock:
            return [op.to_dict() for op in self._history[-20:]]


_coordinator: OperationCoordinator | None = None


def get_coordinator() -> OperationCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = OperationCoordinator()
    return _coordinator


def reset_coordinator() -> None:
    global _coordinator
    _coordinator = None
