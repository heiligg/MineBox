#!/usr/bin/env python3
"""Isolated MineBox pushbutton hardware test (BCM GPIO17, internal pull-up).

Wiring:
  button COM  -> GND
  button NO   -> GPIO17 (physical pin 11)
  Do NOT wire the button to 3.3V or 5V when using pull_up=True.
"""

from __future__ import annotations

import argparse
import time

from gpiozero import Button

BUTTON_GPIO = 17
# Classic debounce: accept a new level only after it has been unchanged this long.
DEBOUNCE_S = 0.04
# Ignore new clicks briefly after a completed click (kills release bounce).
LOCKOUT_S = 0.25
POLL_S = 0.002


def run_test(debounce_s: float, lockout_s: float) -> int:
    button = Button(BUTTON_GPIO, pull_up=True, bounce_time=None)
    press_count = 0

    # Stable logical state (False = released / pulled up).
    stable_pressed = bool(button.is_pressed)
    last_raw = stable_pressed
    last_change = time.monotonic()
    awaiting_release = False
    held_at = 0.0
    unlock_at = 0.0

    print("MineBox button test (classic debounce)")
    print(f"  BCM GPIO{BUTTON_GPIO}  pull_up=True")
    print(f"  debounce={debounce_s*1000:.0f}ms  lockout={lockout_s*1000:.0f}ms")
    print("  Wiring: COM->GND, NO->GPIO17. No 3.3V/5V on the switch.")
    print(
        "  Idle: "
        + (
            "PRESSED/shorted — check wiring (should be released)"
            if stable_pressed
            else "released (OK)"
        )
    )
    print("  Click the button. Ctrl+C to exit.")
    print()

    try:
        while True:
            now = time.monotonic()
            raw = bool(button.is_pressed)

            if raw != last_raw:
                last_raw = raw
                last_change = now

            # Only accept a new stable level after debounce quiet time.
            if (
                raw != stable_pressed
                and (now - last_change) >= debounce_s
                and now >= unlock_at
            ):
                stable_pressed = raw

                if stable_pressed and not awaiting_release:
                    press_count += 1
                    awaiting_release = True
                    held_at = now
                    print(f"[{press_count}] PRESSED", flush=True)
                elif (not stable_pressed) and awaiting_release:
                    held_ms = int((now - held_at) * 1000)
                    awaiting_release = False
                    unlock_at = now + lockout_s
                    print(
                        f"[{press_count}] RELEASED  (held ~{held_ms} ms) — one click",
                        flush=True,
                    )
                    print(flush=True)

            time.sleep(POLL_S)
    except KeyboardInterrupt:
        print("\nExiting.")
        return 0


def run_raw(seconds: float = 15.0) -> int:
    button = Button(BUTTON_GPIO, pull_up=True, bounce_time=None)
    print(f"Raw GPIO{BUTTON_GPIO} monitor for {seconds:.0f}s (Ctrl+C to stop)")
    print("Press once and count DOWN/UP flips.")
    print()
    last = bool(button.is_pressed)
    flips = 0
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            now = bool(button.is_pressed)
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
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MineBox GPIO17 button test")
    parser.add_argument("--raw", action="store_true", help="Show raw pin flips")
    parser.add_argument(
        "--debounce",
        type=float,
        default=DEBOUNCE_S,
        help=f"Debounce seconds (default {DEBOUNCE_S})",
    )
    parser.add_argument(
        "--lockout",
        type=float,
        default=LOCKOUT_S,
        help=f"Post-click lockout seconds (default {LOCKOUT_S})",
    )
    args = parser.parse_args()
    if args.raw:
        return run_raw()
    return run_test(
        debounce_s=max(0.01, args.debounce),
        lockout_s=max(0.05, args.lockout),
    )


if __name__ == "__main__":
    raise SystemExit(main())
