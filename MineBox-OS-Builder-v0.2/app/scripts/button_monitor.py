#!/usr/bin/env python3
"""Live level monitor for MineBox right-button debugging.

Prints GPIO27 (and a few neighbor pins) once per second, and immediately
on any change. Use a jumper from the pin to GND to prove the pin works.
"""

from __future__ import annotations

import time

from gpiozero import DigitalInputDevice

# BCM -> physical pin on 40-pin header
PINS = {
    17: 11,  # left (known working)
    27: 13,  # expected right
    22: 15,  # often confused with 13
    23: 16,
    24: 18,
    18: 12,
    10: 19,
    9: 21,
    11: 23,
}


def main() -> int:
    devices: dict[int, DigitalInputDevice] = {}
    last: dict[int, int] = {}

    print("MineBox GPIO live monitor")
    print("  Expected right button: BCM27 = physical pin 13")
    print("  Test: jumper pin 13 to GND — line should flip to LOW")
    print("  Ctrl+C to exit")
    print()

    for bcm, phys in PINS.items():
        try:
            # pull_up=True: open=1, short-to-GND=0
            dev = DigitalInputDevice(bcm, pull_up=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip BCM{bcm} (pin {phys}): {exc}")
            continue
        devices[bcm] = dev
        last[bcm] = int(dev.value)
        print(f"  BCM{bcm:2d} phys={phys:2d} idle={last[bcm]} ({'HIGH/up' if last[bcm] else 'LOW/down'})")

    print()
    next_status = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            changed = False
            for bcm, dev in devices.items():
                val = int(dev.value)
                if val != last[bcm]:
                    phys = PINS[bcm]
                    print(
                        f"{time.strftime('%H:%M:%S')}  BCM{bcm} (pin {phys}) "
                        f"{last[bcm]} -> {val}  "
                        f"{'RELEASED' if val else 'PRESSED/SHORT to GND'}",
                        flush=True,
                    )
                    last[bcm] = val
                    changed = True
            if now >= next_status and not changed:
                bits = "  ".join(
                    f"{bcm}:{'H' if last[bcm] else 'L'}" for bcm in sorted(last)
                )
                print(f"{time.strftime('%H:%M:%S')}  {bits}", flush=True)
                next_status = now + 1.0
            time.sleep(0.005)
    except KeyboardInterrupt:
        print("\nExiting.")
        return 0
    finally:
        for dev in devices.values():
            dev.close()


if __name__ == "__main__":
    raise SystemExit(main())
