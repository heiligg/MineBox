#!/usr/bin/env python3
"""MineBox dual pushbutton hardware test.

Left:  BCM GPIO17 (active low, internal pull-up) — physical pin 11
Right: BCM GPIO27 (active low, internal pull-up) — physical pin 13

Wiring per button:
  COM -> GND
  NO  -> that button's GPIO
  Do NOT wire the switch to 3.3V or 5V when using pull_up=True.

Use --scan to discover which GPIO actually moves when you press a button.
"""

from __future__ import annotations

import argparse
import time

from gpiozero import Button

LEFT_GPIO = 17
RIGHT_GPIO = 27
# Classic debounce: accept a new level only after it has been unchanged this long.
DEBOUNCE_S = 0.04
# Ignore new edges briefly after a completed click (kills release bounce).
LOCKOUT_S = 0.25
POLL_S = 0.002
# Common header pins people wire by mistake (BCM numbers).
SCAN_GPIOS = (17, 27, 22, 23, 24, 5, 6, 16, 26, 13, 19, 20, 21)


class DebouncedButton:
    """Poll a gpiozero Button with classic edge debounce."""

    def __init__(self, gpio: int, name: str) -> None:
        self.gpio = gpio
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

    def close(self) -> None:
        self.button.close()


def run_test(left_gpio: int, right_gpio: int) -> int:
    left = DebouncedButton(left_gpio, "Left")
    right = DebouncedButton(right_gpio, "Right")

    print("MineBox dual button test")
    print(f"  Left  BCM GPIO{left_gpio}  (pull_up, active low)  [phys pin 11 if GPIO17]")
    print(f"  Right BCM GPIO{right_gpio}  (pull_up, active low)  [phys pin 13 if GPIO27]")
    print(f"  debounce={DEBOUNCE_S*1000:.0f}ms  lockout={LOCKOUT_S*1000:.0f}ms")
    print(
        "  Idle left:  "
        + ("PRESSED/shorted" if left.stable_pressed else "released (OK)")
    )
    print(
        "  Idle right: "
        + ("PRESSED/shorted" if right.stable_pressed else "released (OK)")
    )
    print("  Tip: if Right never prints, run:  python3 ~/button_test.py --scan")
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


def run_scan(seconds: float = 20.0) -> int:
    """Watch several GPIOs; print which one changes when you press a button."""
    buttons: dict[int, Button] = {}
    last: dict[int, bool] = {}
    print("GPIO scan — press LEFT, then RIGHT, once each.")
    print(f"Watching BCM {', '.join(str(g) for g in SCAN_GPIOS)} for {seconds:.0f}s")
    print()
    try:
        for gpio in SCAN_GPIOS:
            try:
                btn = Button(gpio, pull_up=True, bounce_time=None)
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
    print("\nDone. Use the GPIO that flipped for that physical button.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MineBox dual button test")
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Discover which GPIO moves when you press a button",
    )
    parser.add_argument("--left", type=int, default=LEFT_GPIO, help="Left BCM GPIO")
    parser.add_argument("--right", type=int, default=RIGHT_GPIO, help="Right BCM GPIO")
    parser.add_argument(
        "--scan-seconds",
        type=float,
        default=20.0,
        help="How long --scan watches (default 20)",
    )
    args = parser.parse_args()
    if args.scan:
        return run_scan(seconds=max(5.0, args.scan_seconds))
    return run_test(left_gpio=args.left, right_gpio=args.right)


if __name__ == "__main__":
    raise SystemExit(main())
