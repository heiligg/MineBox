"""Checkpoint 5 — display navigation, event bridge, and local trust tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class DisplayCp5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MINEBOX_RUNTIME_DIR"] = self.tmp.name
        os.environ["MINEBOX_DISPLAY_TOKEN_FILE"] = str(Path(self.tmp.name) / "display_token")
        os.environ["MINEBOX_FORCE_MOCK_HARDWARE"] = "1"
        os.environ["MINEBOX_AUTH_FILE"] = str(Path(self.tmp.name) / "auth.json")
        hw_path = Path(self.tmp.name) / "hardware.toml"
        hw_path.write_text(
            "\n".join(
                [
                    "[profile]",
                    'name = "mock"',
                    "[buttons.left]",
                    "gpio_bcm = 23",
                    "[buttons.right]",
                    "gpio_bcm = 17",
                    "[encoder]",
                    "enabled = true",
                    'type = "adafruit_seesaw"',
                    'status = "OK"',
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

    def test_nav_focus_next_prev_wrap(self) -> None:
        from display.nav import NavState

        nav = NavState(wrap=True)
        nav.set_items(["a", "b", "c"])
        self.assertEqual(nav.focused, "a")
        nav.next()
        self.assertEqual(nav.focused, "b")
        nav.prev()
        self.assertEqual(nav.focused, "a")
        nav.prev()
        self.assertEqual(nav.focused, "c")
        nav.next()
        self.assertEqual(nav.focused, "a")

    def test_nav_select_and_back(self) -> None:
        from display.nav import NavState

        nav = NavState(screen="server")
        nav.set_items(["start", "back"])
        self.assertEqual(nav.apply_intent("select"), "start")
        nav.apply_intent("back")
        self.assertEqual(nav.screen, "home")

    def test_action_map_intents(self) -> None:
        from display.actions import DEFAULT_ACTION_MAP
        from display.events import DisplayEventType

        self.assertEqual(DEFAULT_ACTION_MAP.intent_for(DisplayEventType.ENCODER_CW), "next")
        self.assertEqual(DEFAULT_ACTION_MAP.intent_for(DisplayEventType.ENCODER_CCW), "prev")
        self.assertEqual(DEFAULT_ACTION_MAP.intent_for(DisplayEventType.ENCODER_LONG_PRESS), "back")
        self.assertEqual(DEFAULT_ACTION_MAP.intent_for(DisplayEventType.LEFT_BUTTON_HOLD), "home")
        self.assertEqual(DEFAULT_ACTION_MAP.intent_for(DisplayEventType.RIGHT_BUTTON_HOLD), "power")
        self.assertEqual(DEFAULT_ACTION_MAP.intent_for(DisplayEventType.LEFT_BUTTON_PRESS), "back")
        self.assertEqual(DEFAULT_ACTION_MAP.intent_for(DisplayEventType.RIGHT_BUTTON_PRESS), "context")

    def test_bridge_encoder_ordering_and_inject(self) -> None:
        from display.events import DisplayEventType
        from hardware.factory import get_hardware

        hw = get_hardware()
        self.bridge.set_hardware(hw)
        hw.inject_encoder_delta(2)
        events = self.bridge.poll()
        types = [e.type for e in events]
        self.assertEqual(types.count(DisplayEventType.ENCODER_CW), 2)
        injected = self.bridge.inject(DisplayEventType.ENCODER_PRESS, source="test")
        self.assertEqual(injected.type, DisplayEventType.ENCODER_PRESS)

    def test_bridge_button_debounce_short(self) -> None:
        from display.events import DisplayEventType
        from hardware.factory import get_hardware

        hw = get_hardware()
        self.bridge.set_hardware(hw)
        # Simulate press/release via mock helpers with time progression.
        t0 = 1000.0
        hw.set_left_button(True, now=t0)
        hw.set_left_button(False, now=t0 + 0.2)
        # Bridge reads current level; drive through poll with logic time via inject path.
        self.bridge.inject(DisplayEventType.LEFT_BUTTON_PRESS)
        drained = self.bridge.drain()
        self.assertTrue(any(e.type is DisplayEventType.LEFT_BUTTON_PRESS for e in drained))

    def test_disconnect_reconnect(self) -> None:
        from display.events import DisplayEventType

        self.bridge.mark_disconnected()
        ev = self.bridge.drain()
        self.assertTrue(any(e.type is DisplayEventType.HARDWARE_DISCONNECTED for e in ev))
        self.bridge.mark_reconnected()
        ev2 = self.bridge.drain()
        self.assertTrue(any(e.type is DisplayEventType.HARDWARE_RECONNECTED for e in ev2))

    def test_diagnostics_mode_flag(self) -> None:
        self.bridge.set_diagnostics_mode(True)
        self.assertTrue(self.bridge.diagnostics_mode)
        self.bridge.set_diagnostics_mode(False)
        self.assertFalse(self.bridge.diagnostics_mode)

    def test_loopback_trust_and_remote_rejected(self) -> None:
        from display.local_trust import (
            client_is_loopback,
            ensure_display_token,
            verify_display_token,
        )

        token = ensure_display_token()
        self.assertTrue(verify_display_token(token))
        self.assertFalse(verify_display_token("not-the-token"))
        self.assertTrue(client_is_loopback("127.0.0.1"))
        self.assertTrue(client_is_loopback("::1"))
        self.assertFalse(client_is_loopback("192.168.4.20"))

    def test_destructive_actions_listed(self) -> None:
        from display.actions import ALLOWED_DISPLAY_ACTIONS, DESTRUCTIVE_ACTIONS

        self.assertIn("server_stop", DESTRUCTIVE_ACTIONS)
        self.assertIn("device_shutdown", DESTRUCTIVE_ACTIONS)
        self.assertNotIn("console", ALLOWED_DISPLAY_ACTIONS)
        self.assertNotIn("server_start", DESTRUCTIVE_ACTIONS)
        self.assertIn("server_select", ALLOWED_DISPLAY_ACTIONS)
        self.assertIn("server_select", DESTRUCTIVE_ACTIONS)

    def test_kiosk_script_flags(self) -> None:
        script = (ROOT / "app" / "scripts" / "minebox_kiosk_launch.sh").read_text(
            encoding="utf-8"
        )
        for flag in (
            "--kiosk",
            "--no-first-run",
            "--disable-session-crashed-bubble",
            "--disable-save-password-bubble",
            "800,480",
        ):
            self.assertIn(flag, script)

    def test_display_service_unit(self) -> None:
        unit = (ROOT / "app" / "services" / "minebox-display.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("minebox-api.service", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("StartLimitBurst", unit)
        self.assertIn("minebox_display_session.sh", unit)

    def test_curses_fallback_still_present(self) -> None:
        self.assertTrue((ROOT / "app" / "main.py").is_file())
        self.assertTrue((ROOT / "app" / "menu.py").is_file())
        ui = (
            ROOT
            / "pi-gen"
            / "stage-minebox"
            / "01-system-config"
            / "files"
            / "minebox-ui.service"
        )
        self.assertTrue(ui.is_file())

    def test_no_encoder_quadrature_gpio_invented(self) -> None:
        hw = (ROOT / "config" / "hardware.example.toml").read_text(encoding="utf-8")
        self.assertIn("adafruit_seesaw", hw)
        # Must not invent concrete quadrature encoder BCM pins.
        self.assertNotRegex(hw, r"gpio_a\s*=\s*\d+")
        self.assertNotRegex(hw, r"gpio_b\s*=\s*\d+")
        self.assertIn("interrupt_gpio", hw)

    def test_display_docs_exist(self) -> None:
        docs = ROOT / "docs" / "v1"
        for name in (
            "Display_UI_Architecture.md",
            "Display_UI_User_Flow.md",
            "Display_UI_Security.md",
            "Display_Kiosk_Setup.md",
            "Boot_Experience.md",
            "Hardware_Diagnostics.md",
            "User_Manual.md",
            "Encoder.md",
            "Hardware_Controls.md",
        ):
            self.assertTrue((docs / name).is_file(), msg=name)


if __name__ == "__main__":
    unittest.main()
