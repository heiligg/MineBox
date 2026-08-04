"""Thermal monitoring with hysteresis (fan GPIO optional / NOT_CONFIGURED)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

LOGGER = logging.getLogger("minebox.thermal")


class ThermalState(str, Enum):
    NORMAL = "NORMAL"
    WARM = "WARM"
    HOT = "HOT"
    CRITICAL = "CRITICAL"
    SENSOR_UNAVAILABLE = "SENSOR_UNAVAILABLE"


@dataclass
class ThermalThresholds:
    warm_c: float = 60.0
    hot_c: float = 75.0
    critical_c: float = 85.0
    # Hysteresis band when cooling down.
    hysteresis_c: float = 3.0


_state = ThermalState.SENSOR_UNAVAILABLE
_last_temp: float | None = None
_last_change_at = 0.0


def thresholds_from_config() -> ThermalThresholds:
    try:
        from core.minebox_config import get_config

        hw = get_config().hardware
        # Map fan thresholds into thermal bands.
        return ThermalThresholds(
            warm_c=float(hw.fan_off_below_c),
            hot_c=float(hw.fan_on_above_c),
            critical_c=float(hw.fan_critical_c),
            hysteresis_c=3.0,
        )
    except Exception:
        return ThermalThresholds()


def classify(temp_c: float | None, previous: ThermalState, thr: ThermalThresholds) -> ThermalState:
    if temp_c is None:
        return ThermalState.SENSOR_UNAVAILABLE

    # Rising: enter higher severity immediately.
    if temp_c >= thr.critical_c:
        return ThermalState.CRITICAL
    if previous is ThermalState.CRITICAL and temp_c > thr.critical_c - thr.hysteresis_c:
        return ThermalState.CRITICAL

    if temp_c >= thr.hot_c:
        return ThermalState.HOT
    if previous is ThermalState.HOT and temp_c > thr.hot_c - thr.hysteresis_c:
        return ThermalState.HOT

    if temp_c >= thr.warm_c:
        return ThermalState.WARM
    if previous is ThermalState.WARM and temp_c > thr.warm_c - thr.hysteresis_c:
        return ThermalState.WARM

    return ThermalState.NORMAL


def read_temperature_c() -> float | None:
    try:
        from hardware.factory import get_hardware

        return get_hardware().read_cpu_temperature_c()
    except Exception:
        pass
    # Fallback sysfs (also used by monitoring.py).
    try:
        from pathlib import Path

        raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text(encoding="utf-8")
        return int(raw.strip()) / 1000.0
    except (OSError, ValueError):
        return None


def update() -> dict[str, Any]:
    global _state, _last_temp, _last_change_at
    thr = thresholds_from_config()
    temp = read_temperature_c()
    new_state = classify(temp, _state, thr)
    if new_state is not _state:
        LOGGER.warning(
            "Thermal state %s → %s (temp=%s)",
            _state.value,
            new_state.value,
            temp,
        )
        _state = new_state
        _last_change_at = time.time()
    _last_temp = temp

    fan_capability = "NOT_CONFIGURED"
    fan_state = "NOT_CONFIGURED"
    throttling = "unavailable"
    try:
        from hardware.factory import get_hardware
        from core.minebox_config import get_config

        hw = get_hardware()
        fan_capability = get_config().hardware.fan_status
        fan_state = hw.get_fan_state().value
        throttling = hw.read_throttling_state()
    except Exception:
        pass

    return {
        "state": _state.value,
        "temperature_c": temp,
        "thresholds": {
            "warm_c": thr.warm_c,
            "hot_c": thr.hot_c,
            "critical_c": thr.critical_c,
            "hysteresis_c": thr.hysteresis_c,
        },
        "fan_capability": fan_capability,
        "fan_state": fan_state,
        "throttling": throttling,
        "last_change_at": _last_change_at or None,
        "note": (
            "Fan GPIO/PWM remains NOT_CONFIGURED until PCB pinout is verified. "
            "Platform cooling may still be active."
        ),
    }


def reset_for_tests() -> None:
    global _state, _last_temp, _last_change_at
    _state = ThermalState.SENSOR_UNAVAILABLE
    _last_temp = None
    _last_change_at = 0.0
