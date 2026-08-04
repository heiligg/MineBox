from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class FeatureStatus(str, Enum):
    OK = "OK"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNSUPPORTED = "UNSUPPORTED"
    UNAVAILABLE = "UNAVAILABLE"
    DEGRADED = "DEGRADED"


class FanState(str, Enum):
    UNKNOWN = "UNKNOWN"
    OFF = "OFF"
    ON = "ON"
    AUTO = "AUTO"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class InputEvent:
    name: str
    pressed: bool
    timestamp: float
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pressed": self.pressed,
            "timestamp": self.timestamp,
            "source": self.source,
        }


@dataclass
class HardwareHealth:
    profile: str
    ok: bool
    gpio_verification: str
    features: dict[str, str] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "ok": self.ok,
            "gpio_verification": self.gpio_verification,
            "features": dict(self.features),
            "messages": list(self.messages),
            "checked_at": self.checked_at,
        }
