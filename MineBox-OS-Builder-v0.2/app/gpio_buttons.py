#!/usr/bin/env python3
"""Physical MineBox buttons → curses key codes.

Reads through the shared hardware HAL when possible so gpiozero does not
double-claim the same BCM lines (API display bridge + curses UI).

Encoder disabled / missing (current appliance default):
  Short Left/Right → KEY_UP / KEY_DOWN (nav)
  Hold Left/Right  → KEY_LEFT / KEY_ENTER (back / select)

Encoder present + enabled (Hardware Rev D):
  Short Left  → KEY_LEFT   (Back)
  Hold Left   → KEY_HOME   (Home / dashboard)
  Short Right → KEY_RIGHT  (Context / quick)
  Hold Right  → KEY_END    (Power menu)

GPIO BCM numbers come from centralized hardware configuration.
Provisional defaults (UNVERIFIED_AGAINST_PCB): left BCM23, right BCM17.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable

from hardware.debounce import DebounceConfig, DebouncedButtonLogic, PressAction

LOGGER = logging.getLogger("minebox.gpio_buttons")

_FALLBACK_LEFT_GPIO = 23
_FALLBACK_RIGHT_GPIO = 17


def _encoder_present() -> bool:
    try:
        from core.minebox_config import get_config
        from hardware.factory import get_hardware

        if not get_config().hardware.encoder_enabled:
            return False
        hw = get_hardware()
        getter = getattr(hw, "encoder_available", None)
        if callable(getter):
            return bool(getter())
    except Exception:  # noqa: BLE001
        pass
    return False


def _load_button_settings() -> tuple[int, int, DebounceConfig]:
    try:
        from core.minebox_config import get_config

        hw = get_config().hardware
        return (
            hw.left_button.gpio_bcm,
            hw.right_button.gpio_bcm,
            DebounceConfig(
                debounce_s=hw.debounce_ms / 1000.0,
                long_press_s=hw.long_press_ms / 1000.0,
                lockout_s=hw.lockout_ms / 1000.0,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Using fallback button GPIOs (config unavailable): %s", exc)
        return (
            _FALLBACK_LEFT_GPIO,
            _FALLBACK_RIGHT_GPIO,
            DebounceConfig(),
        )


class _HalPin:
    """Button level reader backed by RaspberryPi5Hardware / mock HAL."""

    def __init__(self, side: str, logic: DebouncedButtonLogic) -> None:
        self.side = side
        self.logic = logic

    def is_pressed(self) -> bool:
        from hardware.factory import get_hardware

        hw = get_hardware()
        if self.side == "left":
            return bool(hw.read_left_button())
        return bool(hw.read_right_button())

    def close(self) -> None:
        return


class _GpioZeroPin:
    def __init__(self, button, logic: DebouncedButtonLogic) -> None:
        self.button = button
        self.logic = logic

    def is_pressed(self) -> bool:
        return bool(self.button.is_pressed)

    def close(self) -> None:
        try:
            self.button.close()
        except Exception:  # noqa: BLE001
            pass


class ButtonController:
    def __init__(
        self,
        *,
        left_gpio: int | None = None,
        right_gpio: int | None = None,
        debounce: DebounceConfig | None = None,
        key_up: int,
        key_down: int,
        key_back: int,
        key_select: int,
        key_home: int | None = None,
        key_context: int | None = None,
        key_power: int | None = None,
        rev_d: bool | None = None,
    ) -> None:
        cfg_left, cfg_right, cfg_debounce = _load_button_settings()
        self.left_gpio = left_gpio if left_gpio is not None else cfg_left
        self.right_gpio = right_gpio if right_gpio is not None else cfg_right
        self.debounce = debounce or cfg_debounce
        self.key_up = key_up
        self.key_down = key_down
        self.key_back = key_back
        self.key_select = key_select
        self.key_home = key_home if key_home is not None else key_back
        self.key_context = key_context if key_context is not None else key_up
        self.key_power = key_power if key_power is not None else key_select
        self.rev_d = _encoder_present() if rev_d is None else bool(rev_d)
        self._queue: queue.Queue[int] = queue.Queue(maxsize=32)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._left: _HalPin | _GpioZeroPin | None = None
        self._right: _HalPin | _GpioZeroPin | None = None
        self.available = False
        self._source = "none"

    def start(self) -> bool:
        if self._thread is not None:
            return self.available

        # Prefer shared HAL so we do not fight minebox-api for the same lines.
        try:
            from hardware.factory import get_hardware

            hw = get_hardware()
            # Force GPIO init attempt; read returns False if unavailable.
            _ = hw.read_left_button()
            _ = hw.read_right_button()
            snap = {}
            try:
                snap = hw.diagnostic_snapshot()
            except Exception:  # noqa: BLE001
                snap = {}
            gpio_ok = bool(snap.get("gpio_available", True))
            if gpio_ok or snap.get("profile") in {"mock", "raspberry_pi5"}:
                self._left = _HalPin("left", DebouncedButtonLogic(self.debounce))
                self._right = _HalPin("right", DebouncedButtonLogic(self.debounce))
                self._source = "hal"
                self.available = True
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("HAL button path unavailable: %s", exc)

        if not self.available:
            try:
                from gpiozero import Button

                left_btn = Button(self.left_gpio, pull_up=True, bounce_time=None)
                right_btn = Button(self.right_gpio, pull_up=True, bounce_time=None)
                self._left = _GpioZeroPin(left_btn, DebouncedButtonLogic(self.debounce))
                self._right = _GpioZeroPin(right_btn, DebouncedButtonLogic(self.debounce))
                self._source = "gpiozero"
                self.available = True
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Could not claim button GPIOs: %s", exc)
                return False

        self._thread = threading.Thread(
            target=self._run,
            name="minebox-gpio-buttons",
            daemon=True,
        )
        self._thread.start()
        mode = "Rev D secondary" if self.rev_d else "two-button nav"
        LOGGER.info(
            "Buttons via %s (%s): BCM %s/%s",
            self._source,
            mode,
            self.left_gpio,
            self.right_gpio,
        )
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._left is not None:
            self._left.close()
            self._left = None
        if self._right is not None:
            self._right.close()
            self._right = None
        self.available = False

    def pop_key(self) -> int | None:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def _emit(self, key: int) -> None:
        try:
            self._queue.put_nowait(key)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(key)
            except queue.Full:
                pass

    def _handle(
        self,
        pin: _HalPin | _GpioZeroPin,
        now: float,
        on_short: Callable[[], None],
        on_hold: Callable[[], None],
    ) -> None:
        raw = bool(pin.is_pressed())
        action = pin.logic.update(raw, now)
        if action is PressAction.SHORT:
            on_short()
        elif action is PressAction.LONG:
            on_hold()

    def _run(self) -> None:
        assert self._left is not None and self._right is not None
        poll_s = max(0.001, self.debounce.debounce_s / 8.0)
        while not self._stop.is_set():
            # Re-check encoder presence occasionally for hot-plug reconnect.
            if int(time.monotonic() * 2) % 10 == 0:
                self.rev_d = _encoder_present()
            now = time.monotonic()
            if self.rev_d:
                self._handle(
                    self._left,
                    now,
                    on_short=lambda: self._emit(self.key_back),
                    on_hold=lambda: self._emit(self.key_home),
                )
                self._handle(
                    self._right,
                    now,
                    on_short=lambda: self._emit(self.key_context),
                    on_hold=lambda: self._emit(self.key_power),
                )
            else:
                self._handle(
                    self._left,
                    now,
                    on_short=lambda: self._emit(self.key_up),
                    on_hold=lambda: self._emit(self.key_back),
                )
                self._handle(
                    self._right,
                    now,
                    on_short=lambda: self._emit(self.key_down),
                    on_hold=lambda: self._emit(self.key_select),
                )
            time.sleep(poll_s)


_controller: ButtonController | None = None


def start_buttons() -> ButtonController | None:
    """Start the global button controller (idempotent)."""
    global _controller
    import curses

    if _controller is not None:
        return _controller if _controller.available else None

    _controller = ButtonController(
        key_up=curses.KEY_UP,
        key_down=curses.KEY_DOWN,
        key_back=curses.KEY_LEFT,
        key_select=curses.KEY_ENTER,
        key_home=curses.KEY_HOME,
        key_context=curses.KEY_RIGHT,
        key_power=curses.KEY_END,
    )
    if not _controller.start():
        _controller = None
        return None
    return _controller


def stop_buttons() -> None:
    global _controller
    if _controller is not None:
        _controller.stop()
        _controller = None


def pop_button_key() -> int | None:
    if _controller is None:
        return None
    return _controller.pop_key()


LEFT_GPIO = _FALLBACK_LEFT_GPIO
RIGHT_GPIO = _FALLBACK_RIGHT_GPIO
