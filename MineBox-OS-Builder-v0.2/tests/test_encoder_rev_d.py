"""Hardware Revision D — Seesaw encoder events, fallback, and ActionMap."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class EncoderRevDTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MINEBOX_RUNTIME_DIR"] = self.tmp.name
        os.environ["MINEBOX_FORCE_MOCK_HARDWARE"] = "1"
        os.environ["MINEBOX_HARDWARE_PROFILE"] = "mock"
        os.environ["MINEBOX_AUTH_FILE"] = str(Path(self.tmp.name) / "auth.json")
        # Rev D encoder tests need encoder enabled (appliance default is off).
        hw_path = Path(self.tmp.name) / "hardware.toml"
        hw_path.write_text(
            "\n".join(
                [
                    "[profile]",
                    'name = "mock"',
                    "[buttons.left]",
                    "gpio_bcm = 23",
                    'short_action = "back"',
                    'long_action = "home"',
                    "[buttons.right]",
                    "gpio_bcm = 17",
                    'short_action = "context"',
                    'long_action = "power"',
                    "[encoder]",
                    "enabled = true",
                    'type = "adafruit_seesaw"',
                    'status = "OK"',
                    "i2c_bus = 1",
                    "address = 0x36",
                    "interrupt_gpio = 24",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["MINEBOX_HARDWARE_CONFIG"] = str(hw_path)
        import sys

        app_dir = str(ROOT / "app")
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)

        from core.minebox_config import clear_config_cache
        from display.bridge import reset_display_bridge_for_tests
        from hardware.factory import reset_hardware

        clear_config_cache()
        reset_hardware()
        self.bridge = reset_display_bridge_for_tests()

    def tearDown(self) -> None:
        from core.minebox_config import clear_config_cache
        from hardware.factory import reset_hardware

        reset_hardware()
        clear_config_cache()
        os.environ.pop("MINEBOX_HARDWARE_CONFIG", None)
        self.tmp.cleanup()

    def _hw(self):
        from hardware.factory import get_hardware

        hw = get_hardware()
        self.bridge.set_hardware(hw)
        return hw

    def test_rotation_cw_ccw(self) -> None:
        from display.events import DisplayEventType

        hw = self._hw()
        hw.inject_encoder_delta(1)
        types = [e.type for e in self.bridge.poll()]
        self.assertIn(DisplayEventType.ENCODER_CW, types)

        hw.inject_encoder_delta(-1)
        types = [e.type for e in self.bridge.poll()]
        self.assertIn(DisplayEventType.ENCODER_CCW, types)

    def test_fast_rotation_capped(self) -> None:
        from display.events import DisplayEventType

        hw = self._hw()
        hw.inject_encoder_delta(20)
        types = [e.type for e in self.bridge.poll()]
        self.assertEqual(types.count(DisplayEventType.ENCODER_CW), 8)

    def test_encoder_press_and_long_press_via_inject(self) -> None:
        from display.events import DisplayEventType

        self.bridge.inject(DisplayEventType.ENCODER_PRESS)
        self.bridge.inject(DisplayEventType.ENCODER_LONG_PRESS)
        drained = self.bridge.drain()
        kinds = [e.type for e in drained]
        self.assertIn(DisplayEventType.ENCODER_PRESS, kinds)
        self.assertIn(DisplayEventType.ENCODER_LONG_PRESS, kinds)

    def test_disconnect_reconnect(self) -> None:
        from display.events import DisplayEventType

        hw = self._hw()
        self.assertTrue(hw.encoder_available())
        # Prime connected state.
        self.bridge.poll()
        hw.disconnect_encoder()
        types = [e.type for e in self.bridge.poll()]
        self.assertIn(DisplayEventType.ENCODER_DISCONNECTED, types)
        self.assertFalse(self.bridge.encoder_connected)

        hw.reconnect_encoder()
        types = [e.type for e in self.bridge.poll()]
        self.assertIn(DisplayEventType.ENCODER_RECONNECTED, types)
        self.assertTrue(self.bridge.encoder_connected)

    def test_fallback_action_map(self) -> None:
        from display.actions import (
            DEFAULT_ACTION_MAP,
            TWO_BUTTON_FALLBACK_ACTION_MAP,
            resolve_action_map,
        )
        from display.events import DisplayEventType

        rev = resolve_action_map(encoder_available=True)
        self.assertEqual(rev.intent_for(DisplayEventType.LEFT_BUTTON_PRESS), "back")
        self.assertEqual(rev.intent_for(DisplayEventType.LEFT_BUTTON_HOLD), "home")
        self.assertEqual(rev.intent_for(DisplayEventType.RIGHT_BUTTON_PRESS), "context")
        self.assertEqual(rev.intent_for(DisplayEventType.RIGHT_BUTTON_HOLD), "power")
        self.assertEqual(rev.intent_for(DisplayEventType.ENCODER_CW), "next")
        self.assertEqual(rev.intent_for(DisplayEventType.ENCODER_CCW), "prev")
        self.assertEqual(rev.intent_for(DisplayEventType.ENCODER_PRESS), "select")
        self.assertIs(DEFAULT_ACTION_MAP, rev)

        fb = resolve_action_map(encoder_available=False)
        self.assertEqual(fb.intent_for(DisplayEventType.LEFT_BUTTON_PRESS), "prev")
        self.assertEqual(fb.intent_for(DisplayEventType.RIGHT_BUTTON_PRESS), "next")
        self.assertEqual(fb.left_button_press, TWO_BUTTON_FALLBACK_ACTION_MAP.left_button_press)

        # Explicit Rev D map constants remain available for docs/tests.
        self.assertEqual(
            DEFAULT_ACTION_MAP.intent_for(DisplayEventType.LEFT_BUTTON_PRESS),
            "back",
        )

    def test_nav_home_context_power(self) -> None:
        from display.nav import NavState

        nav = NavState(screen="server")
        nav.set_items(["a", "b"])
        nav.apply_intent("home")
        self.assertEqual(nav.screen, "home")
        nav.apply_intent("context")
        self.assertEqual(nav.screen, "system")
        nav.apply_intent("power")
        self.assertEqual(nav.screen, "power")

    def test_mock_ignores_inject_when_disconnected(self) -> None:
        hw = self._hw()
        hw.disconnect_encoder()
        hw.inject_encoder_delta(3)
        self.assertEqual(hw.read_encoder_delta(), 0)
        hw.set_encoder_press(True)
        self.assertFalse(hw.read_encoder_press())

    def test_seesaw_config_fields(self) -> None:
        from core.minebox_config import load_config

        cfg = load_config(
            ROOT / "config" / "minebox.example.toml",
            ROOT / "config" / "hardware.example.toml",
        ).hardware
        self.assertTrue(cfg.encoder_enabled)
        self.assertEqual(cfg.encoder_type, "adafruit_seesaw")
        self.assertEqual(cfg.encoder_address, 0x36)
        self.assertEqual(cfg.encoder_i2c_bus, 1)
        self.assertEqual(cfg.encoder_interrupt_gpio, 24)
        self.assertEqual(cfg.encoder_debounce_ms, 15)
        self.assertEqual(cfg.encoder_long_press_ms, 700)
        self.assertEqual(cfg.left_button.short_action, "back")
        self.assertEqual(cfg.right_button.long_action, "power")

    def test_driver_module_importable(self) -> None:
        from hardware.seesaw_encoder import SeesawEncoderConfig, SeesawEncoderDriver

        drv = SeesawEncoderDriver(SeesawEncoderConfig(i2c_bus=99, address=0x36))
        # No bus on this host — must not raise; reports disconnected.
        self.assertFalse(drv.connected)
        self.assertEqual(drv.read_delta(), 0)
        self.assertFalse(drv.read_press())
        snap = drv.diagnostic_snapshot()
        self.assertEqual(snap["product"], 5880)
        drv.close()


if __name__ == "__main__":
    unittest.main()
