"""Central input → navigation/action map for the local display UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from display.events import DisplayEventType


@dataclass(frozen=True)
class ActionMap:
    """Single source of truth for encoder/button → UI intents.

    Hardware Rev D (encoder primary):
      CW → next, CCW → prev, press → select
      Left short → back, Left hold → home
      Right short → context, Right hold → power
    """

    encoder_cw: str = "next"
    encoder_ccw: str = "prev"
    encoder_press: str = "select"
    encoder_long_press: str = "back"
    left_button_press: str = "back"
    left_button_hold: str = "home"
    right_button_press: str = "context"
    right_button_hold: str = "power"
    # Public aliases kept for API / JS compatibility.
    encoder_right: str = "next"
    encoder_left: str = "prev"

    def intent_for(self, event_type: DisplayEventType | str) -> str | None:
        key = event_type.value if isinstance(event_type, DisplayEventType) else str(event_type)
        mapping = {
            DisplayEventType.ENCODER_CW.value: self.encoder_cw,
            DisplayEventType.ENCODER_CCW.value: self.encoder_ccw,
            "ENCODER_RIGHT": self.encoder_cw,
            "ENCODER_LEFT": self.encoder_ccw,
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
            "encoder_cw": self.encoder_cw,
            "encoder_ccw": self.encoder_ccw,
            "encoder_right": self.encoder_cw,
            "encoder_left": self.encoder_ccw,
            "encoder_press": self.encoder_press,
            "encoder_long_press": self.encoder_long_press,
            "left_button_press": self.left_button_press,
            "left_button_hold": self.left_button_hold,
            "right_button_press": self.right_button_press,
            "right_button_hold": self.right_button_hold,
            "scheme": "hardware_rev_d",
            "notes": (
                "Encoder is primary navigation (CW/CCW/press). "
                "Left short=back, left hold=home; "
                "right short=context, right hold=power."
            ),
        }


DEFAULT_ACTION_MAP = ActionMap()

# Used when the Seesaw encoder is missing — temporary two-button navigation.
TWO_BUTTON_FALLBACK_ACTION_MAP = ActionMap(
    encoder_cw="next",
    encoder_ccw="prev",
    encoder_press="select",
    encoder_long_press="back",
    left_button_press="prev",
    left_button_hold="back",
    right_button_press="next",
    right_button_hold="select",
    encoder_right="next",
    encoder_left="prev",
)


def resolve_action_map(*, encoder_available: bool) -> ActionMap:
    """Pick Rev D map when encoder is present; otherwise two-button fallback."""
    return DEFAULT_ACTION_MAP if encoder_available else TWO_BUTTON_FALLBACK_ACTION_MAP


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
