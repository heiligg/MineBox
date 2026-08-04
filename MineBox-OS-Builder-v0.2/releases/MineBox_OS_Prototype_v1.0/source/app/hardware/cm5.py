"""Radxa CM5 placeholder profile — explicit unsupported, never silent success."""

from __future__ import annotations

from typing import Any

from core.minebox_config import HardwareConfig
from hardware.types import FanState, FeatureStatus, HardwareHealth, InputEvent


class CM5HardwarePlaceholder:
    """Future CM5 carrier board profile.

    Methods return UNSUPPORTED / raise clear errors rather than pretending to work.
    """

    profile_name = "cm5"

    def __init__(self, config: HardwareConfig) -> None:
        self.config = config

    def _unsupported(self, feature: str) -> FeatureStatus:
        _ = feature
        return FeatureStatus.UNSUPPORTED

    def read_left_button(self) -> bool:
        raise NotImplementedError("CM5 left button GPIO is not implemented yet.")

    def read_right_button(self) -> bool:
        raise NotImplementedError("CM5 right button GPIO is not implemented yet.")

    def read_encoder_delta(self) -> int:
        raise NotImplementedError("CM5 encoder is not implemented yet.")

    def read_encoder_press(self) -> bool:
        raise NotImplementedError("CM5 encoder press is not implemented yet.")

    def set_left_led(self, on: bool) -> FeatureStatus:
        _ = on
        return self._unsupported("left_led")

    def set_right_led(self, on: bool) -> FeatureStatus:
        _ = on
        return self._unsupported("right_led")

    def read_cpu_temperature_c(self) -> float | None:
        # Temperature sysfs may exist on some hosts; still mark profile unsupported.
        return None

    def set_fan(self, state: FanState) -> FeatureStatus:
        _ = state
        return self._unsupported("fan")

    def get_fan_state(self) -> FanState:
        return FanState.UNSUPPORTED

    def read_throttling_state(self) -> str:
        return "UNSUPPORTED"

    def request_shutdown(self) -> FeatureStatus:
        return FeatureStatus.UNSUPPORTED

    def request_reboot(self) -> FeatureStatus:
        return FeatureStatus.UNSUPPORTED

    def capabilities(self) -> dict[str, str]:
        unsupported = FeatureStatus.UNSUPPORTED.value
        return {
            "left_button": unsupported,
            "right_button": unsupported,
            "encoder": unsupported,
            "left_led": unsupported,
            "right_led": unsupported,
            "fan": unsupported,
            "temperature": unsupported,
            "shutdown": unsupported,
            "reboot": unsupported,
        }

    def health(self) -> HardwareHealth:
        return HardwareHealth(
            profile=self.profile_name,
            ok=False,
            gpio_verification="NOT_IMPLEMENTED",
            features=self.capabilities(),
            messages=[
                "CM5 hardware profile is a placeholder. "
                "All front-panel and power methods are UNSUPPORTED until the carrier board pinout lands."
            ],
        )

    def diagnostic_snapshot(self) -> dict[str, Any]:
        return {
            "profile": self.profile_name,
            "status": FeatureStatus.UNSUPPORTED.value,
            "capabilities": self.capabilities(),
            "message": "CM5 profile not implemented",
        }

    def pop_events(self) -> list[InputEvent]:
        return []

    def close(self) -> None:
        return None
