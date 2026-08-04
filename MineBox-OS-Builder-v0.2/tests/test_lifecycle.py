"""Lifecycle / health / crash-loop tests with mocks."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.states import HealthEvidence, MinecraftState
from services.lifecycle import MinecraftLifecycleManager, reset_lifecycle
from services.operations import OperationConflict, OperationType, get_coordinator, reset_coordinator
from services.system import CommandResult


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MINEBOX_RUNTIME_DIR"] = self.tmp.name
        os.environ["MINEBOX_FORCE_MOCK_HARDWARE"] = "1"
        os.environ["MINEBOX_MC_STARTUP_TIMEOUT"] = "2"
        reset_lifecycle()
        reset_coordinator()

    def tearDown(self) -> None:
        reset_lifecycle()
        reset_coordinator()
        self.tmp.cleanup()

    def test_duplicate_start_rejected(self) -> None:
        mgr = MinecraftLifecycleManager()
        mgr._machine.transition(MinecraftState.STARTING, reason="t", force=True)
        with mock.patch.object(mgr, "_installed", return_value=True):
            result = mgr.start()
        self.assertFalse(result.ok)
        self.assertIn("already starting", result.stderr.lower())

    def test_invalid_start_from_crashed_without_recover(self) -> None:
        mgr = MinecraftLifecycleManager()
        mgr._machine.transition(MinecraftState.CRASHED, reason="boom", force=True)
        with mock.patch.object(mgr, "_installed", return_value=True):
            result = mgr.start()
        self.assertFalse(result.ok)
        self.assertIn("CRASHED", result.stderr)

    def test_process_present_unhealthy_not_running(self) -> None:
        from services import minecraft_health
        from core.states import resolve_minecraft_state

        health = HealthEvidence(process_present=True, service_active=True)
        info = resolve_minecraft_state(installed=True, health=health)
        self.assertEqual(info.value, MinecraftState.ERROR)

        # collect_health uses real probes — mock them.
        with mock.patch.object(
            minecraft_health,
            "process_or_service_active",
            return_value=(True, True),
        ), mock.patch.object(
            minecraft_health, "port_listening", return_value=False
        ), mock.patch.object(
            minecraft_health, "rcon_responsive", return_value=False
        ), mock.patch.object(
            minecraft_health, "recent_log_activity", return_value=(False, None)
        ), mock.patch.object(
            minecraft_health, "startup_marker_present", return_value=False
        ):
            result = minecraft_health.collect_health()
        self.assertFalse(result.healthy)
        self.assertEqual(result.phase, "unhealthy")

    def test_start_sequence_to_running(self) -> None:
        mgr = MinecraftLifecycleManager()
        mgr._machine.transition(MinecraftState.STOPPED, reason="init", force=True)
        from services.minecraft_health import HealthCheckResult

        stopped = HealthCheckResult(
            healthy=False,
            evidence=HealthEvidence(),
            phase="stopped",
        )
        running = HealthCheckResult(
            healthy=True,
            evidence=HealthEvidence(
                process_present=True,
                service_active=True,
                port_listening=True,
                rcon_responsive=True,
            ),
            phase="running",
        )
        with mock.patch.object(mgr, "_installed", return_value=True), mock.patch(
            "services.minecraft.start_service",
            return_value=CommandResult(True, "started"),
        ), mock.patch(
            "services.minecraft_health.collect_health",
            side_effect=[stopped, running, running, running],
        ):
            result = mgr.start()
        self.assertTrue(result.ok)
        self.assertEqual(mgr._machine.value, MinecraftState.RUNNING)

    def test_operation_conflict(self) -> None:
        coord = get_coordinator()
        op = coord.begin(OperationType.BACKUP, step="x")
        with self.assertRaises(OperationConflict):
            coord.begin(OperationType.RESTORE, step="y")
        coord.complete(op.id)

    def test_crash_loop_protection(self) -> None:
        from services import crash_recovery

        crash_recovery.configure(auto_restart=True, max_attempts=2, cooldown_s=10)
        crash_recovery.record_failure("fail1")
        crash_recovery.record_failure("fail2")
        allowed, reason = crash_recovery.should_auto_restart()
        self.assertFalse(allowed)
        self.assertIn("Crash-loop", reason)


if __name__ == "__main__":
    unittest.main()
