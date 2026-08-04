"""Central input → navigation/action map for the local display UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from display.events import DisplayEventType


@dataclass(frozen=True)
class ActionMap:
    """Single source of truth for encoder/button → UI intents."""

    encoder_right: str = "next"
    encoder_left: str = "prev"
    encoder_press: str = "select"
    encoder_long_press: str = "back"
    left_button_press: str = "prev"
    left_button_hold: str = "back"
    right_button_press: str = "next"
    right_button_hold: str = "select"

    def intent_for(self, event_type: DisplayEventType | str) -> str | None:
        key = event_type.value if isinstance(event_type, DisplayEventType) else str(event_type)
        mapping = {
            DisplayEventType.ENCODER_RIGHT.value: self.encoder_right,
            DisplayEventType.ENCODER_LEFT.value: self.encoder_left,
            DisplayEventType.ENCODER_PRESS.value: self.encoder_press,
            DisplayEventType.ENCODER_LONG_PRESS.value: self.encoder_long_press,
            DisplayEventType.LEFT_BUTTON_PRESS.value: self.left_button_press,
            DisplayEventType.LEFT_BUTTON_HOLD.value: self.left_button_hold,
            DisplayEventType.RIGHT_BUTTON_PRESS.value: self.right_button_press,
            DisplayEventType.RIGHT_BUTTON_HOLD.value: self.right_button_hold,
        }
        return mapping.get(key)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "encoder_right": self.encoder_right,
            "encoder_left": self.encoder_left,
            "encoder_press": self.encoder_press,
            "encoder_long_press": self.encoder_long_press,
            "left_button_press": self.left_button_press,
            "left_button_hold": self.left_button_hold,
            "right_button_press": self.right_button_press,
            "right_button_hold": self.right_button_hold,
            "notes": (
                "Short left/right buttons map to prev/next; "
                "hold left = back; hold right = select (v1 configurable defaults)."
            ),
        }


DEFAULT_ACTION_MAP = ActionMap()

# Screens that support idle return to home.
IDLE_RETURN_SCREENS = frozenset(
    {
        "server",
        "server_details",
        "backups",
        "network",
        "system",
        "power",
        "diagnostics",
    }
)

# Actions that require an explicit confirmation screen.
DESTRUCTIVE_ACTIONS = frozenset(
    {
        "server_stop",
        "server_restart",
        "device_reboot",
        "device_shutdown",
    }
)

# Scoped display API actions (no raw console).
ALLOWED_DISPLAY_ACTIONS = frozenset(
    {
        "server_start",
        "server_stop",
        "server_restart",
        "backup_create",
        "services_restart",
        "device_reboot",
        "device_shutdown",
    }
)
