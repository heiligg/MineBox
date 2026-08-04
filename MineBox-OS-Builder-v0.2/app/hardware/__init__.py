"""Hardware abstraction layer for MineBox front-panel and platform I/O."""

from hardware.factory import get_hardware, reset_hardware
from hardware.types import FeatureStatus, HardwareHealth, InputEvent

__all__ = [
    "FeatureStatus",
    "HardwareHealth",
    "InputEvent",
    "get_hardware",
    "reset_hardware",
]
