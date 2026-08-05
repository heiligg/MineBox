"""Raspberry Pi 5 hardware profile.

Button BCM numbers come only from HardwareConfig (provisional until PCB verified).
Hardware Rev D: Adafruit Seesaw encoder (Product 5880) over I²C.
LED / fan GPIO remain NOT_CONFIGURED until PCB pinout is verified.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from core.minebox_config import HardwareConfig
from hardware.types import FanState, FeatureStatus, HardwareHealth, InputEvent

LOGGER = logging.getLogger("minebox.hardware.pi5")


class RaspberryPi5Hardware:
    profile_name = "raspberry_pi5"

    def __init__(self, config: HardwareConfig) -> None:
        self.config = config
        self._left_btn = None
        self._right_btn = None
        self._gpio_available = False
        self._gpio_error: str | None = None
        self._encoder = None
        self._encoder_warn_logged = False
        self._events: list[InputEvent] = []
        self._cached_press = False
        self._init_gpio()
        self._init_encoder()

    def _init_gpio(self) -> None:
        try:
            from gpiozero import Button
        except Exception as exc:  # noqa: BLE001
            self._gpio_error = f"gpiozero unavailable: {exc}"
            LOGGER.warning(self._gpio_error)
            return

        pull_up = self.config.pull == "up"
        try:
            self._left_btn = Button(
                self.config.left_button.gpio_bcm,
                pull_up=pull_up,
                bounce_time=None,
            )
            self._right_btn = Button(
                self.config.right_button.gpio_bcm,
                pull_up=pull_up,
                bounce_time=None,
            )
            self._gpio_available = True
            LOGGER.info(
                "Pi5 buttons claimed from config (UNVERIFIED_AGAINST_PCB): "
                "left BCM%s right BCM%s active_level=%s",
                self.config.left_button.gpio_bcm,
                self.config.right_button.gpio_bcm,
                self.config.active_level,
            )
        except Exception as exc:  # noqa: BLE001
            self._gpio_error = f"Could not claim button GPIOs: {exc}"
            LOGGER.warning(self._gpio_error)
            self._close_buttons()

    def _init_encoder(self) -> None:
        if not self.config.encoder_enabled:
            return
        if self.config.encoder_type not in {"adafruit_seesaw", "mock"}:
            return
        try:
            from hardware.seesaw_encoder import SeesawEncoderConfig, SeesawEncoderDriver

            self._encoder = SeesawEncoderDriver(
                SeesawEncoderConfig(
                    i2c_bus=self.config.encoder_i2c_bus,
                    address=self.config.encoder_address,
                    interrupt_gpio=self.config.encoder_interrupt_gpio,
                    rotation_step=self.config.encoder_rotation_step,
                    debounce_ms=self.config.encoder_debounce_ms,
                    long_press_ms=self.config.encoder_long_press_ms,
                )
            )
            if not self._encoder.connected and not self._encoder_warn_logged:
                self._encoder_warn_logged = True
                LOGGER.warning(
                    "Seesaw encoder not detected at boot (bus=%s addr=0x%02X). "
                    "Falling back to two-button navigation; boot continues.",
                    self.config.encoder_i2c_bus,
                    self.config.encoder_address,
                )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Encoder init failed (boot continues): %s", exc)
            self._encoder = None

    def _close_buttons(self) -> None:
        for btn in (self._left_btn, self._right_btn):
            if btn is not None:
                try:
                    btn.close()
                except Exception:  # noqa: BLE001
                    pass
        self._left_btn = None
        self._right_btn = None
        self._gpio_available = False

    def encoder_available(self) -> bool:
        if self._encoder is None:
            return False
        try:
            return bool(self._encoder.connected)
        except Exception:
            return False

    def read_left_button(self) -> bool:
        if not self._gpio_available or self._left_btn is None:
            return False
        pressed = bool(self._left_btn.is_pressed)
        self._events.append(
            InputEvent("left", pressed, time.monotonic(), source="pi5")
        )
        return pressed

    def read_right_button(self) -> bool:
        if not self._gpio_available or self._right_btn is None:
            return False
        pressed = bool(self._right_btn.is_pressed)
        self._events.append(
            InputEvent("right", pressed, time.monotonic(), source="pi5")
        )
        return pressed

    def read_encoder_delta(self) -> int:
        if self._encoder is None:
            return 0
        try:
            delta, pressed = self._encoder.poll()
            self._cached_press = pressed
            return int(delta)
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("encoder delta read failed: %s", exc)
            return 0

    def read_encoder_press(self) -> bool:
        if self._encoder is None:
            return False
        try:
            return bool(self._encoder.read_press())
        except Exception:
            return bool(self._cached_press)

    def set_left_led(self, on: bool) -> FeatureStatus:
        _ = on
        status = self.config.left_led_status
        return FeatureStatus[status] if status in FeatureStatus.__members__ else FeatureStatus.NOT_CONFIGURED

    def set_right_led(self, on: bool) -> FeatureStatus:
        _ = on
        status = self.config.right_led_status
        return FeatureStatus[status] if status in FeatureStatus.__members__ else FeatureStatus.NOT_CONFIGURED

    def read_cpu_temperature_c(self) -> float | None:
        thermal = Path("/sys/class/thermal/thermal_zone0/temp")
        try:
            raw = thermal.read_text(encoding="utf-8").strip()
            return int(raw) / 1000.0
        except (OSError, ValueError):
            return None

    def set_fan(self, state: FanState) -> FeatureStatus:
        _ = state
        if self.config.fan_status in FeatureStatus.__members__:
            return FeatureStatus[self.config.fan_status]
        return FeatureStatus.NOT_CONFIGURED

    def get_fan_state(self) -> FanState:
        if self.config.fan_mode == "platform":
            return FanState.AUTO if self.read_cpu_temperature_c() is not None else FanState.UNKNOWN
        if self.config.fan_status == "NOT_CONFIGURED":
            return FanState.NOT_CONFIGURED
        if self.config.fan_status == "UNSUPPORTED":
            return FanState.UNSUPPORTED
        return FanState.UNKNOWN

    def read_throttling_state(self) -> str:
        try:
            result = subprocess.run(
                ["vcgencmd", "get_throttled"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        return "unavailable"

    def request_shutdown(self) -> FeatureStatus:
        return self._systemctl_power("poweroff")

    def request_reboot(self) -> FeatureStatus:
        return self._systemctl_power("reboot")

    def _systemctl_power(self, action: str) -> FeatureStatus:
        try:
            result = subprocess.run(
                ["sudo", "-n", "/usr/bin/systemctl", action],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return FeatureStatus.OK
            LOGGER.warning("systemctl %s failed: %s", action, (result.stderr or "").strip())
            return FeatureStatus.UNAVAILABLE
        except (OSError, subprocess.SubprocessError) as exc:
            LOGGER.warning("systemctl %s error: %s", action, exc)
            return FeatureStatus.UNAVAILABLE

    def capabilities(self) -> dict[str, str]:
        button_status = (
            FeatureStatus.OK.value
            if self._gpio_available
            else FeatureStatus.UNAVAILABLE.value
        )
        if not self.config.encoder_enabled:
            enc = self.config.encoder_status
        elif self.encoder_available():
            enc = FeatureStatus.OK.value
        else:
            enc = FeatureStatus.UNAVAILABLE.value
        return {
            "left_button": button_status,
            "right_button": button_status,
            "encoder": enc,
            "left_led": self.config.left_led_status,
            "right_led": self.config.right_led_status,
            "fan": self.config.fan_status
            if self.config.fan_mode != "platform"
            else FeatureStatus.DEGRADED.value,
            "temperature": (
                FeatureStatus.OK.value
                if self.read_cpu_temperature_c() is not None
                else FeatureStatus.UNAVAILABLE.value
            ),
            "shutdown": FeatureStatus.OK.value,
            "reboot": FeatureStatus.OK.value,
        }

    def health(self) -> HardwareHealth:
        messages = []
        if self._gpio_error:
            messages.append(self._gpio_error)
        messages.append(
            "Button GPIOs are provisional (UNVERIFIED_AGAINST_PCB) until "
            "docs/v1/Hardware_Pinout.md is source-verified."
        )
        if self.config.encoder_enabled and not self.encoder_available():
            messages.append(
                "Seesaw encoder missing or disconnected — using two-button navigation fallback."
            )
        elif self.encoder_available():
            messages.append("Seesaw encoder (Product 5880) active as primary navigation.")
        if self.config.left_led_status == "NOT_CONFIGURED":
            messages.append("Illuminated LEDs NOT_CONFIGURED.")
        if self.config.fan_status == "NOT_CONFIGURED":
            messages.append("Fan GPIO/PWM NOT_CONFIGURED; using platform cooling if available.")
        return HardwareHealth(
            profile=self.profile_name,
            ok=True,
            gpio_verification=self.config.verification,
            features=self.capabilities(),
            messages=messages,
        )

    def diagnostic_snapshot(self) -> dict[str, Any]:
        enc_snap = None
        if self._encoder is not None:
            try:
                enc_snap = self._encoder.diagnostic_snapshot()
            except Exception as exc:  # noqa: BLE001
                enc_snap = {"error": str(exc)}
        return {
            "profile": self.profile_name,
            "left_button": self.read_left_button() if self._gpio_available else None,
            "right_button": self.read_right_button() if self._gpio_available else None,
            "encoder_press": self.read_encoder_press() if self.encoder_available() else None,
            "encoder_available": self.encoder_available(),
            "encoder": enc_snap,
            "encoder_status": self.capabilities().get("encoder"),
            "left_led_status": self.config.left_led_status,
            "right_led_status": self.config.right_led_status,
            "fan": self.get_fan_state().value,
            "temperature_c": self.read_cpu_temperature_c(),
            "throttling": self.read_throttling_state(),
            "gpio_available": self._gpio_available,
            "gpio_error": self._gpio_error,
            "gpio": {
                "left_bcm": self.config.left_button.gpio_bcm,
                "right_bcm": self.config.right_button.gpio_bcm,
                "verification": self.config.verification,
                "encoder_interrupt_bcm": self.config.encoder_interrupt_gpio,
            },
            "capabilities": self.capabilities(),
        }

    def pop_events(self) -> list[InputEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def close(self) -> None:
        self._close_buttons()
        if self._encoder is not None:
            try:
                self._encoder.close()
            except Exception:  # noqa: BLE001
                pass
            self._encoder = None
