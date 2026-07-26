#!/usr/bin/python3
"""Force the Pi 5 Active Cooler to full speed briefly, then restore.

The firmware thermal governor can overwrite cooling_device cur_state within
1-2 seconds, so this helper prefers pinctrl FAN_PWM force, and otherwise
re-asserts cur_state/pwm for the whole test window.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
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


def _require_root() -> None:
    import os

    if os.geteuid() != 0:
        print(
            "Fan test must run as root via sudo (minebox-fan-test).",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _rpm_paths() -> list[Path]:
    paths: list[Path] = []
    platform_fan = Path("/sys/devices/platform/cooling_fan")
    if platform_fan.is_dir():
        paths.extend(sorted(platform_fan.glob("hwmon/hwmon*/fan1_input")))
    class_hwmon = Path("/sys/class/hwmon")
    if class_hwmon.is_dir():
        for path in sorted(class_hwmon.glob("hwmon*/fan1_input")):
            if path not in paths:
                paths.append(path)
    return paths


def _read_rpm() -> int | None:
    best: int | None = None
    for path in _rpm_paths():
        value = _read_int(path)
        if value is None:
            continue
        if best is None or value > best:
            best = value
    return best


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


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _pinctrl_force(seconds: int) -> tuple[bool, int | None]:
    pinctrl = shutil.which("pinctrl")
    if not pinctrl:
        return False, None

    check = _run([pinctrl, "FAN_PWM"])
    if check.returncode != 0:
        return False, None

    peak = _read_rpm() or 0
    forced = _run([pinctrl, "FAN_PWM", "op", "dl"])
    if forced.returncode != 0:
        detail = (forced.stderr or forced.stdout or "").strip()
        print(f"pinctrl force failed: {detail}", file=sys.stderr)
        return False, None

    try:
        deadline = time.time() + seconds
        while time.time() < deadline:
            time.sleep(0.4)
            rpm = _read_rpm()
            if rpm is not None and rpm > peak:
                peak = rpm
    finally:
        restore = _run([pinctrl, "FAN_PWM", "a0"])
        if restore.returncode != 0:
            print(
                "warning: could not restore FAN_PWM to PWM mode "
                f"({(restore.stderr or restore.stdout or '').strip()})",
                file=sys.stderr,
            )

    return True, peak


def _hold_sysfs(seconds: int) -> tuple[bool, int | None]:
    peak = _read_rpm() or 0

    for device in _cooling_devices():
        cur_path = device / "cur_state"
        max_path = device / "max_state"
        previous = _read_int(cur_path)
        maximum = _read_int(max_path)
        if previous is None or maximum is None or maximum < 1:
            continue
        try:
            deadline = time.time() + seconds
            while time.time() < deadline:
                _write_int(cur_path, maximum)
                time.sleep(0.35)
                rpm = _read_rpm()
                if rpm is not None and rpm > peak:
                    peak = rpm
        except PermissionError as error:
            print(f"Permission denied writing {cur_path}: {error}", file=sys.stderr)
            return False, peak
        finally:
            try:
                _write_int(cur_path, previous)
            except OSError as error:
                print(f"warning: could not restore fan state: {error}", file=sys.stderr)
        print(
            f"ok method=cooling_device device={device.name} "
            f"max={maximum} seconds={seconds} peak_rpm={peak}"
        )
        return True, peak

    for pwm in _pwm_paths():
        previous = _read_int(pwm)
        if previous is None:
            continue
        try:
            deadline = time.time() + seconds
            while time.time() < deadline:
                _write_int(pwm, 255)
                time.sleep(0.35)
                rpm = _read_rpm()
                if rpm is not None and rpm > peak:
                    peak = rpm
        except PermissionError as error:
            print(f"Permission denied writing {pwm}: {error}", file=sys.stderr)
            return False, peak
        finally:
            try:
                _write_int(pwm, previous)
            except OSError as error:
                print(f"warning: could not restore pwm: {error}", file=sys.stderr)
        print(f"ok method=pwm path={pwm} seconds={seconds} peak_rpm={peak}")
        return True, peak

    return False, peak if peak else None


def run_test(seconds: int) -> int:
    _require_root()
    seconds = max(3, min(seconds, 20))
    before = _read_rpm()

    ok, peak = _pinctrl_force(seconds)
    if ok:
        print(
            f"ok method=pinctrl seconds={seconds} "
            f"before_rpm={before} peak_rpm={peak}"
        )
        return 0

    ok, peak = _hold_sysfs(seconds)
    if ok:
        return 0

    print(
        "No writable cooling fan control found "
        "(expected Pi 5 Active Cooler sysfs/pinctrl).",
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
    try:
        return run_test(args.seconds)
    except SystemExit as exit_error:
        code = exit_error.code
        return int(code) if isinstance(code, int) else 1
    except OSError as error:
        print(f"Fan test failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
