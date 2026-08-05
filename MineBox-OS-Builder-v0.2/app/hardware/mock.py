"""Mock hardware profile for development computers and CI."""

from __future__ import annotations

import time
from typing import Any

from core.minebox_config import HardwareConfig
from hardware.debounce import DebounceConfig, DebouncedButtonLogic, PressAction
from hardware.types import FanState, FeatureStatus, HardwareHealth, InputEvent


class MockHardware:
    profile_name = "mock"

    def __init__(self, config: HardwareConfig) -> None:
        self.config = config
        self._left = False
        self._right = False
        self._encoder_press = False
        self._encoder_delta = 0
        self._encoder_present = bool(config.encoder_enabled)
        self._fan = FanState.OFF
        self._temp_c = 42.0
        self._left_led = False
        self._right_led = False
        self._events: list[InputEvent] = []
        debounce = DebounceConfig(
            debounce_s=config.debounce_ms / 1000.0,
            long_press_s=config.long_press_ms / 1000.0,
            lockout_s=config.lockout_ms / 1000.0,
        )
        self._left_logic = DebouncedButtonLogic(debounce)
        self._right_logic = DebouncedButtonLogic(debounce)
        self._shutdown_requested = False
        self._reboot_requested = False

    def set_left_button(self, pressed: bool, *, now: float | None = None) -> PressAction:
        return self._apply_button("left", self._left_logic, pressed, now)

    def set_right_button(self, pressed: bool, *, now: float | None = None) -> PressAction:
        return self._apply_button("right", self._right_logic, pressed, now)

    def _apply_button(
        self,
        name: str,
        logic: DebouncedButtonLogic,
        pressed: bool,
        now: float | None,
    ) -> PressAction:
        if name == "left":
            self._left = pressed
        else:
            self._right = pressed
        ts = time.monotonic() if now is None else now
        action = logic.update(pressed, ts)
        self._events.append(InputEvent(name=name, pressed=pressed, timestamp=ts, source="mock"))
        return action

    def inject_encoder_delta(self, delta: int) -> None:
        """Inject CW (positive) or CCW (negative) rotation steps."""
        if not self._encoder_present:
            return
        self._encoder_delta += int(delta)

    def set_encoder_press(self, pressed: bool) -> None:
        if not self._encoder_present:
            self._encoder_press = False
            return
        self._encoder_press = bool(pressed)

    def disconnect_encoder(self) -> None:
        self._encoder_present = False
        self._encoder_press = False
        self._encoder_delta = 0

    def reconnect_encoder(self) -> None:
        self._encoder_present = True

    def encoder_available(self) -> bool:
        return bool(self._encoder_present and self.config.encoder_enabled)

    def read_left_button(self) -> bool:
        return self._left

    def read_right_button(self) -> bool:
        return self._right

    def read_encoder_delta(self) -> int:
        if not self.encoder_available():
            self._encoder_delta = 0
            return 0
        delta = self._encoder_delta
        self._encoder_delta = 0
        return delta

    def read_encoder_press(self) -> bool:
        if not self.encoder_available():
            return False
        return self._encoder_press

    def set_left_led(self, on: bool) -> FeatureStatus:
        if self.config.left_led_status in {"NOT_CONFIGURED", "UNSUPPORTED"}:
            return FeatureStatus[self.config.left_led_status]
        self._left_led = bool(on)
        return FeatureStatus.OK

    def set_right_led(self, on: bool) -> FeatureStatus:
        if self.config.right_led_status in {"NOT_CONFIGURED", "UNSUPPORTED"}:
            return FeatureStatus[self.config.right_led_status]
        self._right_led = bool(on)
        return FeatureStatus.OK

    def read_cpu_temperature_c(self) -> float | None:
        return self._temp_c

    def set_temperature(self, temp_c: float) -> None:
        self._temp_c = float(temp_c)

    def set_fan(self, state: FanState) -> FeatureStatus:
        if self.config.fan_status in {"NOT_CONFIGURED", "UNSUPPORTED"}:
            self._fan = state
            return FeatureStatus[self.config.fan_status]
        self._fan = state
        return FeatureStatus.OK

    def get_fan_state(self) -> FanState:
        if self.config.fan_status == "NOT_CONFIGURED":
            return FanState.NOT_CONFIGURED
        if self.config.fan_status == "UNSUPPORTED":
            return FanState.UNSUPPORTED
        return self._fan

    def read_throttling_state(self) -> str:
        return "none"

    def request_shutdown(self) -> FeatureStatus:
        self._shutdown_requested = True
        return FeatureStatus.OK

    def request_reboot(self) -> FeatureStatus:
        self._reboot_requested = True
        return FeatureStatus.OK

    def capabilities(self) -> dict[str, str]:
        enc = (
            FeatureStatus.OK.value
            if self.encoder_available()
            else (
                FeatureStatus.UNAVAILABLE.value
                if self.config.encoder_enabled
                else self.config.encoder_status
            )
        )
        return {
            "left_button": FeatureStatus.OK.value,
            "right_button": FeatureStatus.OK.value,
            "encoder": enc,
            "left_led": self.config.left_led_status,
            "right_led": self.config.right_led_status,
            "fan": self.config.fan_status,
            "temperature": FeatureStatus.OK.value,
            "shutdown": FeatureStatus.OK.value,
            "reboot": FeatureStatus.OK.value,
        }

    def health(self) -> HardwareHealth:
        messages = ["Mock hardware active (no real GPIO)."]
        if self.config.encoder_enabled and not self._encoder_present:
            messages.append("Encoder disconnected (fallback two-button navigation).")
        return HardwareHealth(
            profile=self.profile_name,
            ok=True,
            gpio_verification=self.config.verification,
            features=self.capabilities(),
            messages=messages,
        )

    def diagnostic_snapshot(self) -> dict[str, Any]:
        return {
            "profile": self.profile_name,
            "left_button": self._left,
            "right_button": self._right,
            "encoder_press": self._encoder_press,
            "encoder_available": self.encoder_available(),
            "pending_encoder_delta": self._encoder_delta,
            "left_led": self._left_led,
            "right_led": self._right_led,
            "fan": self.get_fan_state().value,
            "temperature_c": self._temp_c,
            "shutdown_requested": self._shutdown_requested,
            "reboot_requested": self._reboot_requested,
            "capabilities": self.capabilities(),
            "gpio": {
                "left_bcm": self.config.left_button.gpio_bcm,
                "right_bcm": self.config.right_button.gpio_bcm,
                "verification": self.config.verification,
                "encoder": self.config.encoder_status,
                "encoder_type": self.config.encoder_type,
                "encoder_address": f"0x{self.config.encoder_address:02x}",
                "leds": {
                    "left": self.config.left_led_status,
                    "right": self.config.right_led_status,
                },
                "fan": self.config.fan_status,
            },
        }

    def pop_events(self) -> list[InputEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def close(self) -> None:
        return None
