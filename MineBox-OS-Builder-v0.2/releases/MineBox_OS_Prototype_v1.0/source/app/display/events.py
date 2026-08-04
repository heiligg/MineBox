"""Canonical display input event types (HAL → UI)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class DisplayEventType(str, Enum):
    ENCODER_LEFT = "ENCODER_LEFT"
    ENCODER_RIGHT = "ENCODER_RIGHT"
    ENCODER_PRESS = "ENCODER_PRESS"
    ENCODER_LONG_PRESS = "ENCODER_LONG_PRESS"
    LEFT_BUTTON_PRESS = "LEFT_BUTTON_PRESS"
    LEFT_BUTTON_HOLD = "LEFT_BUTTON_HOLD"
    RIGHT_BUTTON_PRESS = "RIGHT_BUTTON_PRESS"
    RIGHT_BUTTON_HOLD = "RIGHT_BUTTON_HOLD"
    HARDWARE_DISCONNECTED = "HARDWARE_DISCONNECTED"
    HARDWARE_RECONNECTED = "HARDWARE_RECONNECTED"


@dataclass(frozen=True)
class DisplayEvent:
    type: DisplayEventType
    timestamp: float
    source: str = "hal"
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "timestamp": self.timestamp,
            "source": self.source,
            "sequence": self.sequence,
        }


def now_ts() -> float:
    return time.monotonic()
