"""Configuration validation tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.minebox_config import ConfigError, clear_config_cache, load_config, parse_hardware


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_MINEBOX = ROOT / "config" / "minebox.example.toml"
EXAMPLE_HARDWARE = ROOT / "config" / "hardware.example.toml"


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_config_cache()
        os.environ["MINEBOX_FORCE_MOCK_HARDWARE"] = "1"
        os.environ["MINEBOX_HARDWARE_PROFILE"] = "mock"

    def tearDown(self) -> None:
        clear_config_cache()

    def test_example_configs_validate(self) -> None:
        cfg = load_config(EXAMPLE_MINEBOX, EXAMPLE_HARDWARE)
        self.assertEqual(cfg.device_name, "MineBox")
        self.assertEqual(cfg.api_port, 8080)
        self.assertEqual(cfg.hardware.left_button.gpio_bcm, 23)
        self.assertEqual(cfg.hardware.right_button.gpio_bcm, 17)
        self.assertEqual(cfg.hardware.verification, "UNVERIFIED_AGAINST_PCB")
        self.assertEqual(cfg.hardware.encoder_status, "OK")
        self.assertTrue(cfg.hardware.encoder_enabled)
        self.assertEqual(cfg.hardware.encoder_type, "adafruit_seesaw")
        self.assertEqual(cfg.hardware.encoder_address, 0x36)
        self.assertEqual(cfg.hardware.left_button.short_action, "back")
        self.assertEqual(cfg.hardware.right_button.long_action, "power")
        self.assertEqual(cfg.hardware.left_led_status, "NOT_CONFIGURED")
        self.assertEqual(cfg.hardware.fan_status, "NOT_CONFIGURED")

    def test_invalid_fan_hysteresis(self) -> None:
        with self.assertRaises(ConfigError):
            parse_hardware(
                {
                    "profile": {"name": "mock"},
                    "buttons": {
                        "left": {"gpio_bcm": 23},
                        "right": {"gpio_bcm": 17},
                    },
                    "fan": {"off_below_c": 70, "on_above_c": 60, "status": "NOT_CONFIGURED"},
                }
            )

    def test_reject_invented_encoder_pins_when_not_configured(self) -> None:
        with self.assertRaises(ConfigError):
            parse_hardware(
                {
                    "profile": {"name": "mock"},
                    "buttons": {
                        "left": {"gpio_bcm": 23},
                        "right": {"gpio_bcm": 17},
                    },
                    "encoder": {
                        "status": "NOT_CONFIGURED",
                        "gpio_a": 5,
                        "gpio_b": 6,
                    },
                }
            )

    def test_invalid_toml_readable_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.toml"
            bad.write_text("this is not = [valid\n", encoding="utf-8")
            with self.assertRaises(ConfigError) as ctx:
                load_config(bad, EXAMPLE_HARDWARE)
            self.assertIn("Invalid TOML", str(ctx.exception))

    def test_gpio_provisional_status(self) -> None:
        cfg = load_config(EXAMPLE_MINEBOX, EXAMPLE_HARDWARE)
        self.assertEqual(cfg.hardware.left_button.verification, "UNVERIFIED_AGAINST_PCB")
        self.assertEqual(cfg.hardware.right_button.verification, "UNVERIFIED_AGAINST_PCB")


if __name__ == "__main__":
    unittest.main()
