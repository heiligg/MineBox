#!/usr/bin/env python3
"""Isolated MineBox pushbutton hardware test (BCM GPIO17, internal pull-up).

Wiring:
  button COM  -> GND
  button NO   -> GPIO17 (physical pin 11)
  Do NOT wire the button to 3.3V or 5V when using pull_up=True.
"""

from __future__ import annotations

import time

from gpiozero import Button

BUTTON_GPIO = 17
# gpiozero hardware debounce
BOUNCE_TIME = 0.05
# Must stay pressed/released this long before we count the edge (seconds).
STABLE_TIME = 0.12
# Ignore activity after a completed click (seconds).
POST_CLICK_LOCKOUT = 0.35


def wait_stable(button: Button, want_pressed: bool, stable_s: float) -> None:
    """Block until pin matches want_pressed continuously for stable_s."""
    stable_since: float | None = None
    while True:
        if bool(button.is_pressed) == want_pressed:
            now = time.monotonic()
            if stable_since is None:
                stable_since = now
            elif now - stable_since >= stable_s:
                return
        else:
            stable_since = None
        time.sleep(0.005)


def main() -> int:
    button = Button(BUTTON_GPIO, pull_up=True, bounce_time=BOUNCE_TIME)
    press_count = 0

    print("MineBox button test (stable-edge debounce)")
    print(f"  BCM GPIO{BUTTON_GPIO}  pull_up=True  bounce={BOUNCE_TIME}s")
    print(f"  stable={STABLE_TIME}s  lockout={POST_CLICK_LOCKOUT}s")
    print("  Wiring: COM->GND, NO->GPIO17. No 3.3V/5V on the switch.")
    print(f"  Idle state now: {'PRESSED (shorted to GND?)' if button.is_pressed else 'released (OK)'}")
    print("  One physical click => one PRESSED + one RELEASED.")
    print("  Ctrl+C to exit.")
    print()

    try:
        while True:
            wait_stable(button, want_pressed=True, stable_s=STABLE_TIME)
            press_count += 1
            held_at = time.monotonic()
            print(f"[{press_count}] PRESSED")

            wait_stable(button, want_pressed=False, stable_s=STABLE_TIME)
            held_ms = int((time.monotonic() - held_at) * 1000)
            print(f"[{press_count}] RELEASED  (held ~{held_ms} ms) — one click")
            print()
            time.sleep(POST_CLICK_LOCKOUT)
    except KeyboardInterrupt:
        print("\nExiting.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
