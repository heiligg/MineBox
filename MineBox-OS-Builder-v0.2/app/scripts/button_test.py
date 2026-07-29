#!/usr/bin/env python3
"""Isolated MineBox pushbutton hardware test (BCM GPIO17, internal pull-up).

Wiring:
  button COM  -> GND
  button NO   -> GPIO17 (physical pin 11)
  Do NOT wire the button to 3.3V or 5V when using pull_up=True.

Note: gpiozero's bounce_time only filters callbacks. Reading .is_pressed still
sees raw bounce, so this script uses its own stable-state machine.
"""

from __future__ import annotations

import argparse
import time

from gpiozero import Button

BUTTON_GPIO = 17
# How long the pin must stay in a new state before we accept it (seconds).
STABLE_TIME = 0.20
# After a completed click, ignore the pin completely (seconds).
POST_CLICK_LOCKOUT = 0.60
SAMPLE_DT = 0.005


def sample_pressed(button: Button, window_s: float = 0.05) -> bool:
    """Majority vote over a short window (filters sub-ms bounce)."""
    votes = 0
    total = max(1, int(window_s / SAMPLE_DT))
    for _ in range(total):
        if button.is_pressed:
            votes += 1
        time.sleep(SAMPLE_DT)
    return votes * 2 >= total


def wait_for_state(button: Button, want_pressed: bool, stable_s: float) -> float:
    """Wait until majority-sampled state matches want_pressed for stable_s.

    Returns how long the accepted state had already been held (approx).
    """
    stable_since: float | None = None
    while True:
        pressed = sample_pressed(button)
        if pressed == want_pressed:
            now = time.monotonic()
            if stable_since is None:
                stable_since = now
            elif now - stable_since >= stable_s:
                return now - stable_since
        else:
            stable_since = None


def run_test(stable_s: float, lockout_s: float) -> int:
    # bounce_time=None: we debounce ourselves via sampling + stability window.
    button = Button(BUTTON_GPIO, pull_up=True, bounce_time=None)
    press_count = 0

    idle = sample_pressed(button)
    print("MineBox button test (software state-machine debounce)")
    print(f"  BCM GPIO{BUTTON_GPIO}  pull_up=True")
    print(f"  stable={stable_s:.2f}s  lockout={lockout_s:.2f}s")
    print("  Wiring: COM->GND, NO->GPIO17. No 3.3V/5V on the switch.")
    print(
        "  Idle: "
        + (
            "PRESSED/shorted — check wiring (should be released)"
            if idle
            else "released (OK)"
        )
    )
    print("  One physical click => one PRESSED + one RELEASED.")
    print("  Ctrl+C to exit.")
    print()

    try:
        while True:
            wait_for_state(button, want_pressed=True, stable_s=stable_s)
            press_count += 1
            held_at = time.monotonic()
            print(f"[{press_count}] PRESSED", flush=True)

            wait_for_state(button, want_pressed=False, stable_s=stable_s)
            held_ms = int((time.monotonic() - held_at) * 1000)
            print(
                f"[{press_count}] RELEASED  (held ~{held_ms} ms) — one click",
                flush=True,
            )
            print(flush=True)

            # Hard lockout: do not sample the pin at all (release bounce dies here).
            time.sleep(lockout_s)
    except KeyboardInterrupt:
        print("\nExiting.")
        return 0


def run_raw(seconds: float = 15.0) -> int:
    """Print every raw level change for diagnosing wiring/noise."""
    button = Button(BUTTON_GPIO, pull_up=True, bounce_time=None)
    print(f"Raw GPIO{BUTTON_GPIO} monitor for {seconds:.0f}s (Ctrl+C to stop)")
    print("Press the button once and watch how many flips appear.")
    print()
    last = button.is_pressed
    flips = 0
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            now = button.is_pressed
            if now != last:
                flips += 1
                print(
                    f"{time.strftime('%H:%M:%S')}  "
                    f"{'DOWN' if now else 'UP'}  (flip #{flips})",
                    flush=True,
                )
                last = now
            time.sleep(0.001)
    except KeyboardInterrupt:
        pass
    print(f"\nTotal raw flips: {flips}")
    if flips > 4:
        print(
            "Lots of flips on one click = noisy switch/wiring. "
            "Shorten wires, twist with GND, add 0.1uF across the switch, "
            "or use a better switch."
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MineBox GPIO17 button test")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Show raw pin flips instead of debounced clicks",
    )
    parser.add_argument(
        "--stable",
        type=float,
        default=STABLE_TIME,
        help=f"Stable window seconds (default {STABLE_TIME})",
    )
    parser.add_argument(
        "--lockout",
        type=float,
        default=POST_CLICK_LOCKOUT,
        help=f"Post-click lockout seconds (default {POST_CLICK_LOCKOUT})",
    )
    args = parser.parse_args()
    if args.raw:
        return run_raw()
    return run_test(stable_s=max(0.05, args.stable), lockout_s=max(0.1, args.lockout))


if __name__ == "__main__":
    raise SystemExit(main())
