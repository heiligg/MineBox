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
        self.assertEqual(cfg.hardware.left_button.gpio_bcm, 17)
        self.assertEqual(cfg.hardware.right_button.gpio_bcm, 27)
        self.assertEqual(cfg.hardware.verification, "SOURCE_VERIFIED")
        self.assertEqual(cfg.hardware.encoder_status, "OK")
        self.assertTrue(cfg.hardware.encoder_enabled)
        self.assertEqual(cfg.hardware.encoder_type, "adafruit_seesaw")
        self.assertEqual(cfg.hardware.encoder_address, 0x36)
        self.assertEqual(cfg.hardware.encoder_interrupt_gpio, 22)
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

    def test_gpio_source_verified(self) -> None:
        cfg = load_config(EXAMPLE_MINEBOX, EXAMPLE_HARDWARE)
        self.assertEqual(cfg.hardware.left_button.verification, "SOURCE_VERIFIED")
        self.assertEqual(cfg.hardware.right_button.verification, "SOURCE_VERIFIED")
        self.assertEqual(cfg.hardware.left_button.physical_pin, 11)
        self.assertEqual(cfg.hardware.right_button.physical_pin, 13)


    def test_ota_rewrites_legacy_button_gpios(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "minebox_update_apply",
            ROOT / "app" / "scripts" / "minebox_update_apply.py",
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hardware.toml"
            path.write_text(
                "\n".join(
                    [
                        "[buttons.left]",
                        "gpio_bcm = 23",
                        "physical_pin = 16",
                        'short_action = "back"',
                        'long_action = "home"',
                        "[buttons.right]",
                        "gpio_bcm = 17",
                        "physical_pin = 11",
                        'short_action = "context"',
                        'long_action = "power"',
                        "[encoder]",
                        "enabled = true",
                        'status = "OK"',
                        "i2c_bus = 1",
                        "address = 0x36",
                        "interrupt_gpio = 24",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            module.ensure_encoder_rev_d_config(path)
            text = path.read_text(encoding="utf-8")
        self.assertIn("gpio_bcm = 17", text)
        self.assertIn("gpio_bcm = 27", text)
        self.assertIn("interrupt_gpio = 22", text)
        self.assertNotIn("gpio_bcm = 23", text)
        self.assertNotIn("interrupt_gpio = 24", text)


if __name__ == "__main__":
    unittest.main()
