"""HAL mock / debounce / unresolved feature tests."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from core.minebox_config import clear_config_cache, load_config
from hardware.cm5 import CM5HardwarePlaceholder
from hardware.debounce import DebounceConfig, DebouncedButtonLogic, PressAction
from hardware.factory import create_hardware, reset_hardware
from hardware.mock import MockHardware
from hardware.pi5 import RaspberryPi5Hardware
from hardware.types import FanState, FeatureStatus


ROOT = Path(__file__).resolve().parents[1]


class DebounceTests(unittest.TestCase):
    def test_debounce_ignores_bounce(self) -> None:
        logic = DebouncedButtonLogic(DebounceConfig(debounce_s=0.04, long_press_s=0.45))
        self.assertEqual(logic.update(True, 0.0), PressAction.NONE)
        self.assertEqual(logic.update(False, 0.01), PressAction.NONE)
        self.assertEqual(logic.update(True, 0.02), PressAction.NONE)
        # Stable press after debounce window from last change at 0.02
        self.assertEqual(logic.update(True, 0.07), PressAction.NONE)
        # Short release
        self.assertEqual(logic.update(False, 0.10), PressAction.NONE)
        self.assertEqual(logic.update(False, 0.15), PressAction.SHORT)

    def test_long_press(self) -> None:
        logic = DebouncedButtonLogic(DebounceConfig(debounce_s=0.01, long_press_s=0.20))
        self.assertEqual(logic.update(True, 0.0), PressAction.NONE)
        self.assertEqual(logic.update(True, 0.02), PressAction.NONE)  # debounced down
        self.assertEqual(logic.update(True, 0.25), PressAction.LONG)
        # Only once
        self.assertEqual(logic.update(True, 0.30), PressAction.NONE)


class HardwareTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_hardware()
        clear_config_cache()
        os.environ["MINEBOX_FORCE_MOCK_HARDWARE"] = "1"
        os.environ["MINEBOX_HARDWARE_PROFILE"] = "mock"
        self.cfg = load_config(
            ROOT / "config" / "minebox.example.toml",
            ROOT / "config" / "hardware.example.toml",
        ).hardware

    def tearDown(self) -> None:
        reset_hardware()
        clear_config_cache()

    def test_mock_button_events(self) -> None:
        hw = MockHardware(self.cfg)
        self.assertFalse(hw.read_left_button())
        hw.set_left_button(True, now=0.0)
        hw.set_left_button(True, now=0.05)
        action = hw.set_left_button(False, now=0.10)
        # May be SHORT depending on debounce; ensure events recorded.
        self.assertTrue(hw.pop_events())
        self.assertIn(action, {PressAction.NONE, PressAction.SHORT})

    def test_unresolved_led_fan_encoder_capability(self) -> None:
        hw = MockHardware(self.cfg)
        # Encoder enabled in Rev D example — mock presents as available.
        self.assertTrue(hw.encoder_available())
        self.assertEqual(hw.read_encoder_delta(), 0)
        self.assertEqual(hw.set_left_led(True), FeatureStatus.NOT_CONFIGURED)
        self.assertEqual(hw.set_right_led(True), FeatureStatus.NOT_CONFIGURED)
        self.assertEqual(hw.set_fan(FanState.ON), FeatureStatus.NOT_CONFIGURED)
        caps = hw.capabilities()
        self.assertEqual(caps["encoder"], "OK")
        self.assertEqual(caps["left_led"], "NOT_CONFIGURED")
        self.assertEqual(caps["fan"], "NOT_CONFIGURED")

    def test_pi5_degrades_without_gpio(self) -> None:
        hw = RaspberryPi5Hardware(self.cfg)
        # On Windows/dev hosts gpiozero may be missing — must not crash.
        health = hw.health()
        self.assertTrue(health.ok)
        self.assertEqual(health.gpio_verification, "SOURCE_VERIFIED")
        self.assertEqual(hw.set_left_led(True), FeatureStatus.NOT_CONFIGURED)
        hw.close()

    def test_cm5_unsupported(self) -> None:
        hw = CM5HardwarePlaceholder(self.cfg)
        self.assertEqual(hw.set_fan(FanState.ON), FeatureStatus.UNSUPPORTED)
        with self.assertRaises(NotImplementedError):
            hw.read_left_button()
        health = hw.health()
        self.assertFalse(health.ok)
        self.assertIn("placeholder", health.messages[0].lower())

    def test_factory_mock_forced(self) -> None:
        hw = create_hardware(self.cfg)
        self.assertEqual(hw.profile_name, "mock")


if __name__ == "__main__":
    unittest.main()
