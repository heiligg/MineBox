#!/usr/bin/env python3
"""MineBox dual pushbutton hardware test.

Left:  BCM GPIO23 (active low, internal pull-up) — physical pin 16
Right: BCM GPIO17 (active low, internal pull-up) — physical pin 11

Wiring per button (active-low):
  COM -> GND (e.g. physical pin 14)
  NO  -> that button's GPIO
  Do NOT wire the switch to 3.3V or 5V.

If a button never fires:
  1) python3 ~/button_test.py --scan
  2) Jumper that button's signal pin to GND (pin 14).
  3) Try: python3 ~/button_test.py --right-active-high
"""

from __future__ import annotations

import argparse
import time

from gpiozero import Button

LEFT_GPIO = 23
RIGHT_GPIO = 17
DEBOUNCE_S = 0.04
LOCKOUT_S = 0.25
POLL_S = 0.002
SCAN_GPIOS = (17, 23, 27, 22, 24, 5, 6, 16, 26, 13, 19, 20, 21, 18, 12)


class DebouncedButton:
    """Poll a gpiozero Button with classic edge debounce."""

    def __init__(self, gpio: int, name: str, *, pull_up: bool) -> None:
        self.gpio = gpio
        self.name = name
        self.pull_up = pull_up
        # active_state must be set when pull_up is False
        kwargs = {"pull_up": pull_up, "bounce_time": None}
        if not pull_up:
            kwargs["active_state"] = True
        self.button = Button(gpio, **kwargs)
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

    def close(self) -> None:
        self.button.close()


def run_test(left_gpio: int, right_gpio: int, *, right_pull_up: bool) -> int:
    left = DebouncedButton(left_gpio, "Left", pull_up=True)
    right = DebouncedButton(right_gpio, "Right", pull_up=right_pull_up)

    print("MineBox dual button test")
    print(f"  Left  BCM GPIO{left_gpio}  pull_up=True   (phys pin 16 if GPIO23)")
    print(
        f"  Right BCM GPIO{right_gpio}  pull_up={right_pull_up}  "
        f"(phys pin 11 if GPIO17)"
    )
    print(f"  debounce={DEBOUNCE_S*1000:.0f}ms  lockout={LOCKOUT_S*1000:.0f}ms")
    print(
        "  Idle left:  "
        + ("PRESSED/shorted" if left.stable_pressed else "released (OK)")
    )
    print(
        "  Idle right: "
        + ("PRESSED/shorted" if right.stable_pressed else "released (OK)")
    )
    print("  Hardware check: jumper pin 11 to pin 14 (GND) — should print Right pressed.")
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
    finally:
        left.close()
        right.close()


def run_scan(seconds: float, *, pull_up: bool) -> int:
    buttons: dict[int, Button] = {}
    last: dict[int, bool] = {}
    mode = "pull-up/active-low" if pull_up else "pull-down/active-high"
    print(f"GPIO scan ({mode}) — press LEFT, then RIGHT.")
    print(f"Watching BCM {', '.join(str(g) for g in SCAN_GPIOS)} for {seconds:.0f}s")
    print()
    try:
        for gpio in SCAN_GPIOS:
            try:
                kwargs = {"pull_up": pull_up, "bounce_time": None}
                if not pull_up:
                    kwargs["active_state"] = True
                btn = Button(gpio, **kwargs)
            except Exception as exc:  # noqa: BLE001
                print(f"  skip GPIO{gpio}: {exc}")
                continue
            buttons[gpio] = btn
            last[gpio] = bool(btn.is_pressed)
            print(f"  GPIO{gpio}: idle={'DOWN' if last[gpio] else 'UP'}")

        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for gpio, btn in buttons.items():
                now = bool(btn.is_pressed)
                if now != last[gpio]:
                    print(
                        f"{time.strftime('%H:%M:%S')}  GPIO{gpio} -> "
                        f"{'DOWN' if now else 'UP'}",
                        flush=True,
                    )
                    last[gpio] = now
            time.sleep(0.002)
    except KeyboardInterrupt:
        print("\nScan stopped.")
    finally:
        for btn in buttons.values():
            btn.close()
    print("\nDone. Note which GPIO flipped for the Right button.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MineBox dual button test")
    parser.add_argument("--scan", action="store_true", help="Discover which GPIO moves")
    parser.add_argument(
        "--scan-active-high",
        action="store_true",
        help="Scan assuming buttons short to 3.3V (pull-down)",
    )
    parser.add_argument("--left", type=int, default=LEFT_GPIO)
    parser.add_argument("--right", type=int, default=RIGHT_GPIO)
    parser.add_argument(
        "--right-active-high",
        action="store_true",
        help="Right button shorts to 3.3V instead of GND",
    )
    parser.add_argument("--scan-seconds", type=float, default=30.0)
    args = parser.parse_args()

    if args.scan or args.scan_active_high:
        return run_scan(
            seconds=max(5.0, args.scan_seconds),
            pull_up=not args.scan_active_high,
        )
    return run_test(
        left_gpio=args.left,
        right_gpio=args.right,
        right_pull_up=not args.right_active_high,
    )


if __name__ == "__main__":
    raise SystemExit(main())
