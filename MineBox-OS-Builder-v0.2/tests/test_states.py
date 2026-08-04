"""Minecraft state model and transition tests."""

from __future__ import annotations

import unittest

from core.states import (
    HealthEvidence,
    InvalidTransition,
    MinecraftState,
    MinecraftStateMachine,
    can_transition,
    is_healthy_running,
    resolve_minecraft_state,
    validate_transition,
)


class StateModelTests(unittest.TestCase):
    def test_valid_transitions(self) -> None:
        self.assertTrue(can_transition(MinecraftState.STOPPED, MinecraftState.STARTING))
        self.assertTrue(can_transition(MinecraftState.STARTING, MinecraftState.RUNNING))
        self.assertTrue(can_transition(MinecraftState.RUNNING, MinecraftState.STOPPING))
        self.assertTrue(can_transition(MinecraftState.RUNNING, MinecraftState.BACKING_UP))

    def test_invalid_transitions(self) -> None:
        self.assertFalse(can_transition(MinecraftState.NOT_INSTALLED, MinecraftState.RUNNING))
        with self.assertRaises(InvalidTransition):
            validate_transition(MinecraftState.NOT_INSTALLED, MinecraftState.RUNNING)

    def test_state_machine_rejects_invalid(self) -> None:
        sm = MinecraftStateMachine(MinecraftState.STOPPED)
        result = sm.transition(MinecraftState.RUNNING, reason="skip start")
        self.assertFalse(result.ok)
        self.assertEqual(sm.value, MinecraftState.STOPPED)

    def test_state_machine_allows_valid(self) -> None:
        sm = MinecraftStateMachine(MinecraftState.STOPPED)
        result = sm.transition(MinecraftState.STARTING, reason="user start")
        self.assertTrue(result.ok)
        result = sm.transition(
            MinecraftState.RUNNING,
            reason="healthy",
            health=HealthEvidence(process_present=True, port_listening=True),
        )
        self.assertTrue(result.ok)
        self.assertEqual(sm.value, MinecraftState.RUNNING)

    def test_process_present_but_unhealthy_is_not_running(self) -> None:
        health = HealthEvidence(process_present=True, service_active=True)
        self.assertFalse(is_healthy_running(health))
        info = resolve_minecraft_state(installed=True, health=health)
        self.assertEqual(info.value, MinecraftState.ERROR)
        self.assertIn("PID alone", info.reason)

    def test_healthy_running_requires_evidence(self) -> None:
        health = HealthEvidence(
            process_present=True,
            service_active=True,
            rcon_responsive=True,
        )
        info = resolve_minecraft_state(installed=True, health=health)
        self.assertEqual(info.value, MinecraftState.RUNNING)


if __name__ == "__main__":
    unittest.main()
