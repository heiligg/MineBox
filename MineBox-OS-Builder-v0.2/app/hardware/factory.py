"""Hardware profile factory."""

from __future__ import annotations

import logging
import os
from typing import Any

from core.minebox_config import HardwareConfig, get_config
from hardware.cm5 import CM5HardwarePlaceholder
from hardware.mock import MockHardware
from hardware.pi5 import RaspberryPi5Hardware

LOGGER = logging.getLogger("minebox.hardware")

_instance: Any | None = None


def create_hardware(config: HardwareConfig | None = None):
    if config is None:
        config = get_config().hardware

    # CI / desktop default: never touch real GPIO unless explicitly requested.
    force_mock = os.environ.get("MINEBOX_HARDWARE_PROFILE", "").strip().lower() == "mock"
    if force_mock or os.environ.get("MINEBOX_FORCE_MOCK_HARDWARE", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        LOGGER.info("Using mock hardware profile (forced).")
        return MockHardware(config)

    name = config.profile_name.lower()
    if name == "mock":
        return MockHardware(config)
    if name == "cm5":
        return CM5HardwarePlaceholder(config)
    if name == "raspberry_pi5":
        return RaspberryPi5Hardware(config)

    LOGGER.warning("Unknown hardware profile %r; falling back to mock.", name)
    return MockHardware(config)


def get_hardware(*, reload: bool = False):
    global _instance
    if _instance is None or reload:
        if _instance is not None:
            try:
                _instance.close()
            except Exception:  # noqa: BLE001
                pass
        _instance = create_hardware()
    return _instance


def reset_hardware() -> None:
    global _instance
    if _instance is not None:
        try:
            _instance.close()
        except Exception:  # noqa: BLE001
            pass
    _instance = None
