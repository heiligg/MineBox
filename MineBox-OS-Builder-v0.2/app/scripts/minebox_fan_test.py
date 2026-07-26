#!/usr/bin/python3
"""Force the Pi 5 firmware cooling fan to max briefly, then restore.

Used by the dashboard "Test fan" action. Prefers thermal cooling_device
cur_state, with pwm1 as a fallback.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _write_int(path: Path, value: int) -> None:
    path.write_text(f"{int(value)}\n", encoding="utf-8")


def _cooling_devices() -> list[Path]:
    thermal = Path("/sys/class/thermal")
    if not thermal.is_dir():
        return []
    devices: list[Path] = []
    for device in sorted(thermal.glob("cooling_device*")):
        type_path = device / "type"
        try:
            dtype = (
                type_path.read_text(encoding="utf-8").strip().lower()
                if type_path.is_file()
                else ""
            )
        except OSError:
            dtype = ""
        if "fan" in dtype and (device / "cur_state").is_file():
            devices.append(device)
    return devices


def _pwm_paths() -> list[Path]:
    paths: list[Path] = []
    platform_fan = Path("/sys/devices/platform/cooling_fan")
    if platform_fan.is_dir():
        paths.extend(sorted(platform_fan.glob("hwmon/hwmon*/pwm1")))
    class_hwmon = Path("/sys/class/hwmon")
    if class_hwmon.is_dir():
        for pwm in sorted(class_hwmon.glob("hwmon*/pwm1")):
            if pwm not in paths:
                paths.append(pwm)
    return paths


def run_test(seconds: int) -> int:
    seconds = max(3, min(seconds, 20))
    restored = False

    for device in _cooling_devices():
        cur_path = device / "cur_state"
        max_path = device / "max_state"
        previous = _read_int(cur_path)
        maximum = _read_int(max_path)
        if previous is None or maximum is None or maximum < 1:
            continue
        try:
            _write_int(cur_path, maximum)
            time.sleep(seconds)
        finally:
            try:
                _write_int(cur_path, previous)
                restored = True
            except OSError as error:
                print(f"warning: could not restore fan state: {error}", file=sys.stderr)
        print(f"ok cooling_device={device.name} max={maximum} seconds={seconds}")
        return 0

    for pwm in _pwm_paths():
        previous = _read_int(pwm)
        if previous is None:
            continue
        try:
            _write_int(pwm, 255)
            time.sleep(seconds)
        finally:
            try:
                _write_int(pwm, previous)
                restored = True
            except OSError as error:
                print(f"warning: could not restore pwm: {error}", file=sys.stderr)
        print(f"ok pwm={pwm} seconds={seconds} restored={restored}")
        return 0

    print(
        "No writable cooling fan control found "
        "(expected Pi 5 Active Cooler sysfs).",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seconds",
        type=int,
        default=8,
        help="Seconds to hold the fan at maximum (3-20).",
    )
    args = parser.parse_args()
    return run_test(args.seconds)


if __name__ == "__main__":
    raise SystemExit(main())
