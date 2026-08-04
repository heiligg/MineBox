"""Thermal hysteresis and safe-shutdown coordination tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from services import thermal
from services.operations import reset_coordinator
from services.system import CommandResult
from services.thermal import ThermalState, classify, thresholds_from_config


class ThermalTests(unittest.TestCase):
    def setUp(self) -> None:
        thermal.reset_for_tests()

    def test_threshold_and_hysteresis(self) -> None:
        thr = thermal.ThermalThresholds(warm_c=60, hot_c=75, critical_c=85, hysteresis_c=3)
        self.assertEqual(classify(50, ThermalState.NORMAL, thr), ThermalState.NORMAL)
        self.assertEqual(classify(61, ThermalState.NORMAL, thr), ThermalState.WARM)
        self.assertEqual(classify(76, ThermalState.WARM, thr), ThermalState.HOT)
        self.assertEqual(classify(86, ThermalState.HOT, thr), ThermalState.CRITICAL)
        # Falling: stay HOT until below hot-hysteresis
        self.assertEqual(classify(73, ThermalState.HOT, thr), ThermalState.HOT)
        self.assertEqual(classify(71, ThermalState.HOT, thr), ThermalState.WARM)

    def test_sensor_unavailable(self) -> None:
        thr = thermal.ThermalThresholds()
        self.assertEqual(
            classify(None, ThermalState.NORMAL, thr),
            ThermalState.SENSOR_UNAVAILABLE,
        )

    def test_fan_not_configured_reported(self) -> None:
        with mock.patch.object(thermal, "read_temperature_c", return_value=42.0), mock.patch(
            "hardware.factory.get_hardware"
        ) as hw, mock.patch(
            "core.minebox_config.get_config"
        ) as cfg:
            hw.return_value.get_fan_state.return_value.value = "NOT_CONFIGURED"
            hw.return_value.read_throttling_state.return_value = "none"
            cfg.return_value.hardware.fan_status = "NOT_CONFIGURED"
            cfg.return_value.hardware.fan_off_below_c = 55
            cfg.return_value.hardware.fan_on_above_c = 65
            cfg.return_value.hardware.fan_critical_c = 90
            snap = thermal.update()
        self.assertEqual(snap["fan_capability"], "NOT_CONFIGURED")
        self.assertEqual(snap["state"], "NORMAL")


class ShutdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MINEBOX_RUNTIME_DIR"] = self.tmp.name
        os.environ["MINEBOX_DEV_MODE"] = "1"
        reset_coordinator()

    def tearDown(self) -> None:
        reset_coordinator()
        self.tmp.cleanup()

    def test_shutdown_stops_minecraft_first(self) -> None:
        from services import safe_shutdown

        with mock.patch.object(
            safe_shutdown, "prepare_minecraft_stop", return_value=CommandResult(True, "stopped")
        ) as prep, mock.patch.object(
            safe_shutdown, "_privileged_systemctl", return_value=CommandResult(False, stderr="no sudo")
        ):
            result = safe_shutdown.request_shutdown(reason="test", reboot=False)
        self.assertTrue(result["ok"])
        self.assertTrue(result["minecraft_stopped"])
        prep.assert_called()


if __name__ == "__main__":
    unittest.main()
