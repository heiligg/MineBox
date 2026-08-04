"""Pure debounce + long-press detection (unit-testable, no GPIO)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class PressAction(Enum):
    NONE = auto()
    SHORT = auto()
    LONG = auto()


@dataclass
class DebounceConfig:
    debounce_s: float = 0.04
    long_press_s: float = 0.45
    lockout_s: float = 0.15


class DebouncedButtonLogic:
    """Edge-stable debounce with single long-press fire and post-release lockout."""

    def __init__(self, config: DebounceConfig | None = None) -> None:
        self.config = config or DebounceConfig()
        self.stable_pressed = False
        self.last_raw = False
        self.last_change = 0.0
        self.press_started: float | None = None
        self.hold_fired = False
        self.unlock_at = 0.0

    def update(self, raw_pressed: bool, now: float) -> PressAction:
        if raw_pressed != self.last_raw:
            self.last_raw = raw_pressed
            self.last_change = now

        action = PressAction.NONE

        if (
            raw_pressed != self.stable_pressed
            and (now - self.last_change) >= self.config.debounce_s
            and now >= self.unlock_at
        ):
            self.stable_pressed = raw_pressed
            if self.stable_pressed:
                self.press_started = now
                self.hold_fired = False
            else:
                if (
                    self.press_started is not None
                    and not self.hold_fired
                    and (now - self.press_started) < self.config.long_press_s
                ):
                    action = PressAction.SHORT
                self.press_started = None
                self.hold_fired = False
                self.unlock_at = now + self.config.lockout_s

        if (
            action is PressAction.NONE
            and self.stable_pressed
            and self.press_started is not None
            and not self.hold_fired
            and (now - self.press_started) >= self.config.long_press_s
        ):
            self.hold_fired = True
            action = PressAction.LONG

        return action
