#!/usr/bin/env python3
"""Isolated MineBox pushbutton hardware test (BCM GPIO17, internal pull-up)."""

import time

from gpiozero import Button

# BCM numbering. COM -> GND, NO -> GPIO17. Internal pull-up (not wired to 3.3V/5V).
BUTTON_GPIO = 17
# Hardware debounce inside gpiozero (seconds). Mechanical bounce often lasts 50–200ms.
BOUNCE_TIME = 0.25
# After a full click, ignore edges briefly so release bounce cannot start another press.
POST_CLICK_LOCKOUT = 0.20

button = Button(BUTTON_GPIO, pull_up=True, bounce_time=BOUNCE_TIME)
press_count = 0

print("MineBox button test")
print(
    f"  Watching BCM GPIO{BUTTON_GPIO} "
    f"(internal pull-up, bounce={BOUNCE_TIME}s, lockout={POST_CLICK_LOCKOUT}s)"
)
print("  One physical click should print PRESSED then RELEASED once each.")
print("  Press Ctrl+C to exit.")
print()

try:
    # Sequential wait forces one PRESSED + one RELEASED per physical click
    # (callbacks alone can still double-fire on noisy bounce).
    while True:
        button.wait_for_press()
        press_count += 1
        print(f"[{press_count}] Button PRESSED  (finger down)")

        button.wait_for_release()
        print(f"[{press_count}] Button RELEASED (finger up) — one full click complete")
        print()

        time.sleep(POST_CLICK_LOCKOUT)
except KeyboardInterrupt:
    print("\nExiting.")
