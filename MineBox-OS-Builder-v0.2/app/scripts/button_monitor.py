#!/usr/bin/env python3
"""Live level monitor for MineBox button debugging.

Left:  BCM GPIO17 = header pin 11
Right: BCM GPIO27 = header pin 13 (GND on header pin 9)
"""

from __future__ import annotations

import time

from gpiozero import DigitalInputDevice

# BCM -> physical pin on 40-pin header
PINS = {
    17: 11,  # left SW1
    27: 13,  # right SW2
    22: 15,  # encoder INT
}


def main() -> int:
    devices: dict[int, DigitalInputDevice] = {}
    last: dict[int, int] = {}

    print("MineBox GPIO live monitor")
    print("  Left:  BCM GPIO17 = header pin 11")
    print("  Right: BCM GPIO27 = header pin 13  (GND = header pin 9)")
    print("  Test: jumper pin 13 to pin 9 — GPIO27 should flip (Right)")
    print("  Ctrl+C to exit")
    print()

    for bcm, phys in PINS.items():
        try:
            dev = DigitalInputDevice(bcm, pull_up=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip BCM{bcm} (pin {phys}): {exc}")
            continue
        devices[bcm] = dev
        last[bcm] = int(dev.value)
        print(
            f"  BCM{bcm:2d} phys={phys:2d} idle={last[bcm]} "
            f"({'ACTIVE' if last[bcm] else 'idle'})"
        )

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
                        f"{'PRESSED/SHORT' if val else 'RELEASED'}",
                        flush=True,
                    )
                    last[bcm] = val
                    changed = True
            if now >= next_status and not changed:
                bits = "  ".join(
                    f"{bcm}:{'P' if last[bcm] else '-'}" for bcm in sorted(last)
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
