"""Raspberry Pi 5 hardware profile.

Button BCM numbers come only from HardwareConfig (provisional until PCB verified).
Encoder / LED / fan GPIO are NOT invented — report NOT_CONFIGURED.
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
        self._events: list[InputEvent] = []
        self._init_gpio()

    def _init_gpio(self) -> None:
        try:
            from gpiozero import Button
        except Exception as exc:  # noqa: BLE001
            self._gpio_error = f"gpiozero unavailable: {exc}"
            LOGGER.warning(self._gpio_error)
            return

        pull_up = self.config.pull == "up"
        try:
            # bounce_time=None: debounce handled in higher layers / gpio_buttons.
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
        return 0

    def read_encoder_press(self) -> bool:
        return False

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
            # Platform firmware cooler — report AUTO when temp readable.
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
        return {
            "left_button": button_status,
            "right_button": button_status,
            "encoder": self.config.encoder_status,
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
        if self.config.encoder_status == "NOT_CONFIGURED":
            messages.append("Encoder pins NOT_CONFIGURED (Adafruit 5880).")
        if self.config.left_led_status == "NOT_CONFIGURED":
            messages.append("Illuminated LEDs NOT_CONFIGURED.")
        if self.config.fan_status == "NOT_CONFIGURED":
            messages.append("Fan GPIO/PWM NOT_CONFIGURED; using platform cooling if available.")
        return HardwareHealth(
            profile=self.profile_name,
            ok=True,  # backend must not fail when optional GPIO missing
            gpio_verification=self.config.verification,
            features=self.capabilities(),
            messages=messages,
        )

    def diagnostic_snapshot(self) -> dict[str, Any]:
        return {
            "profile": self.profile_name,
            "left_button": self.read_left_button() if self._gpio_available else None,
            "right_button": self.read_right_button() if self._gpio_available else None,
            "encoder_press": None,
            "encoder_delta": None,
            "encoder_status": self.config.encoder_status,
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
            },
            "capabilities": self.capabilities(),
        }

    def pop_events(self) -> list[InputEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def close(self) -> None:
        self._close_buttons()
