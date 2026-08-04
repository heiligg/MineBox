"""Safe system shutdown / reboot coordination (service layer)."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.secrets_store import redact_secrets
from services.operations import OperationConflict, OperationType, get_coordinator
from services.system import CommandResult

LOGGER = logging.getLogger("minebox.shutdown")


def _runtime_dir() -> Path:
    return Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox"))


def _record(reason: str, action: str) -> None:
    path = _runtime_dir() / "last_shutdown.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            __import__("json").dumps(
                {
                    "action": action,
                    "reason": redact_secrets(reason),
                    "at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _privileged_systemctl(action: str) -> CommandResult:
    # Narrow allowlist — never pass user-controlled shell strings.
    if action not in {"poweroff", "reboot"}:
        return CommandResult(False, stderr="Unsupported power action.")
    try:
        result = subprocess.run(
            ["sudo", "-n", "/usr/bin/systemctl", action],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CommandResult(False, stderr=str(exc))
    if result.returncode != 0:
        return CommandResult(
            False,
            stderr=(result.stderr or result.stdout or f"systemctl {action} failed"),
        )
    return CommandResult(True, f"systemctl {action} requested.")


def prepare_minecraft_stop(timeout_s: float = 60.0) -> CommandResult:
    from services.lifecycle import get_lifecycle
    from services import minecraft

    life = get_lifecycle()
    snap = life.refresh(reason="pre_shutdown")
    state = snap["state"]["value"]
    if state in {"STOPPED", "NOT_INSTALLED"}:
        return CommandResult(True, "Minecraft already stopped.")
    result = life.stop(coordinate=False)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not minecraft.is_running():
            return CommandResult(True, result.stdout or "Minecraft stopped for shutdown.")
        time.sleep(0.5)
    return CommandResult(False, stderr="Minecraft did not stop before shutdown timeout.")


def request_shutdown(*, reason: str = "user", reboot: bool = False) -> dict[str, Any]:
    coordinator = get_coordinator()
    try:
        op = coordinator.begin(OperationType.SHUTDOWN, step="prepare")
    except OperationConflict as exc:
        return {"ok": False, "error": str(exc)}

    action = "reboot" if reboot else "poweroff"
    try:
        coordinator.update(op.id, progress=0.2, step="stop_minecraft")
        stop_result = prepare_minecraft_stop()
        if not stop_result.ok:
            coordinator.complete(op.id, error=stop_result.stderr)
            return {
                "ok": False,
                "error": stop_result.stderr,
                "minecraft_stopped": False,
            }

        # Best-effort: do not start new backups; active backup conflicts already blocked.
        coordinator.update(op.id, progress=0.7, step="record")
        _record(reason, action)

        coordinator.update(op.id, progress=0.9, step=action)
        power = _privileged_systemctl(action)
        if not power.ok:
            # In CI/dev without sudo, report success of coordination path with note.
            if os.environ.get("MINEBOX_DEV_MODE", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                coordinator.complete(op.id)
                return {
                    "ok": True,
                    "action": action,
                    "minecraft_stopped": True,
                    "system_requested": False,
                    "message": (
                        f"Dev mode: Minecraft stopped; system {action} not executed "
                        f"({power.stderr})."
                    ),
                    "reason": reason,
                }
            coordinator.complete(op.id, error=power.stderr)
            return {
                "ok": False,
                "error": power.stderr,
                "minecraft_stopped": True,
                "system_requested": False,
            }

        coordinator.complete(op.id)
        return {
            "ok": True,
            "action": action,
            "minecraft_stopped": True,
            "system_requested": True,
            "message": power.stdout,
            "reason": reason,
        }
    except Exception as exc:  # noqa: BLE001
        coordinator.complete(op.id, error=str(exc))
        return {"ok": False, "error": redact_secrets(str(exc))}
