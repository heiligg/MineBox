#!/usr/bin/env python3
"""MineBox dual pushbutton hardware test.

Left:  BCM GPIO17 (active low, internal pull-up)
Right: BCM GPIO27 (active low, internal pull-up)

Wiring per button:
  COM -> GND
  NO  -> that button's GPIO
  Do NOT wire the switch to 3.3V or 5V when using pull_up=True.
"""

from __future__ import annotations

import time

from gpiozero import Button

LEFT_GPIO = 17
RIGHT_GPIO = 27
# Classic debounce: accept a new level only after it has been unchanged this long.
DEBOUNCE_S = 0.04
# Ignore new edges briefly after a completed click (kills release bounce).
LOCKOUT_S = 0.25
POLL_S = 0.002


class DebouncedButton:
    """Poll a gpiozero Button with classic edge debounce."""

    def __init__(self, gpio: int, name: str) -> None:
        self.name = name
        self.button = Button(gpio, pull_up=True, bounce_time=None)
        self.stable_pressed = bool(self.button.is_pressed)
        self.last_raw = self.stable_pressed
        self.last_change = time.monotonic()
        self.awaiting_release = False
        self.unlock_at = 0.0

    def poll(self, now: float) -> None:
        raw = bool(self.button.is_pressed)
        if raw != self.last_raw:
            self.last_raw = raw
            self.last_change = now

        if (
            raw != self.stable_pressed
            and (now - self.last_change) >= DEBOUNCE_S
            and now >= self.unlock_at
        ):
            self.stable_pressed = raw
            if self.stable_pressed and not self.awaiting_release:
                self.awaiting_release = True
                print(f"{self.name} button pressed", flush=True)
            elif (not self.stable_pressed) and self.awaiting_release:
                self.awaiting_release = False
                self.unlock_at = now + LOCKOUT_S
                print(f"{self.name} button released", flush=True)


def main() -> int:
    left = DebouncedButton(LEFT_GPIO, "Left")
    right = DebouncedButton(RIGHT_GPIO, "Right")

    print("MineBox dual button test")
    print(f"  Left  BCM GPIO{LEFT_GPIO}  (pull_up, active low)")
    print(f"  Right BCM GPIO{RIGHT_GPIO}  (pull_up, active low)")
    print(f"  debounce={DEBOUNCE_S*1000:.0f}ms  lockout={LOCKOUT_S*1000:.0f}ms")
    print(
        "  Idle left:  "
        + ("PRESSED/shorted" if left.stable_pressed else "released (OK)")
    )
    print(
        "  Idle right: "
        + ("PRESSED/shorted" if right.stable_pressed else "released (OK)")
    )
    print("  Ctrl+C to exit.")
    print()

    try:
        while True:
            now = time.monotonic()
            left.poll(now)
            right.poll(now)
            time.sleep(POLL_S)
    except KeyboardInterrupt:
        print("\nExiting.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
