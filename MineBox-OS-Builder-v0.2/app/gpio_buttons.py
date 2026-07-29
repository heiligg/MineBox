#!/usr/bin/env python3
"""Physical MineBox buttons → curses key codes (encoder stand-in).

Until a rotary encoder ships:
  Short Left  → KEY_UP     (encoder CCW / previous)
  Short Right → KEY_DOWN   (encoder CW / next)
  Hold Left   → KEY_LEFT   (Back)
  Hold Right  → KEY_ENTER  (Confirm / click)

Pins (active-low, internal pull-up):
  Left  BCM17 / physical pin 11
  Right BCM23 / physical pin 16
  GND          / physical pin 14
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable

LOGGER = logging.getLogger("minebox.gpio_buttons")

LEFT_GPIO = 17
RIGHT_GPIO = 23
DEBOUNCE_S = 0.04
HOLD_S = 0.45
POLL_S = 0.005
LOCKOUT_S = 0.15


class _DebouncedPin:
    def __init__(self, button) -> None:
        self.button = button
        self.stable_pressed = bool(button.is_pressed)
        self.last_raw = self.stable_pressed
        self.last_change = time.monotonic()
        self.press_started: float | None = None
        self.hold_fired = False
        self.unlock_at = 0.0

    def close(self) -> None:
        try:
            self.button.close()
        except Exception:  # noqa: BLE001
            pass


class ButtonController:
    """Background GPIO poller that emits curses key codes onto a queue."""

    def __init__(
        self,
        *,
        left_gpio: int = LEFT_GPIO,
        right_gpio: int = RIGHT_GPIO,
        hold_s: float = HOLD_S,
        key_up: int,
        key_down: int,
        key_back: int,
        key_select: int,
    ) -> None:
        self.left_gpio = left_gpio
        self.right_gpio = right_gpio
        self.hold_s = hold_s
        self.key_up = key_up
        self.key_down = key_down
        self.key_back = key_back
        self.key_select = key_select
        self._queue: queue.Queue[int] = queue.Queue(maxsize=32)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._left: _DebouncedPin | None = None
        self._right: _DebouncedPin | None = None
        self.available = False

    def start(self) -> bool:
        if self._thread is not None:
            return self.available
        try:
            from gpiozero import Button
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("gpiozero unavailable: %s", exc)
            return False

        try:
            left_btn = Button(self.left_gpio, pull_up=True, bounce_time=None)
            right_btn = Button(self.right_gpio, pull_up=True, bounce_time=None)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not claim button GPIOs: %s", exc)
            return False

        self._left = _DebouncedPin(left_btn)
        self._right = _DebouncedPin(right_btn)
        self.available = True
        self._thread = threading.Thread(
            target=self._run,
            name="minebox-gpio-buttons",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info(
            "Buttons active: short L/R=nav, hold L=back, hold R=confirm "
            "(BCM %s/%s)",
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

    def _update_pin(
        self,
        pin: _DebouncedPin,
        now: float,
        *,
        on_short: Callable[[], None],
        on_hold: Callable[[], None],
    ) -> None:
        raw = bool(pin.button.is_pressed)
        if raw != pin.last_raw:
            pin.last_raw = raw
            pin.last_change = now

        if (
            raw != pin.stable_pressed
            and (now - pin.last_change) >= DEBOUNCE_S
            and now >= pin.unlock_at
        ):
            pin.stable_pressed = raw
            if pin.stable_pressed:
                pin.press_started = now
                pin.hold_fired = False
            else:
                # Released.
                if (
                    pin.press_started is not None
                    and not pin.hold_fired
                    and (now - pin.press_started) < self.hold_s
                ):
                    on_short()
                pin.press_started = None
                pin.hold_fired = False
                pin.unlock_at = now + LOCKOUT_S

        # Hold fires once while still pressed.
        if (
            pin.stable_pressed
            and pin.press_started is not None
            and not pin.hold_fired
            and (now - pin.press_started) >= self.hold_s
        ):
            pin.hold_fired = True
            on_hold()

    def _run(self) -> None:
        assert self._left is not None and self._right is not None
        while not self._stop.is_set():
            now = time.monotonic()
            self._update_pin(
                self._left,
                now,
                on_short=lambda: self._emit(self.key_up),
                on_hold=lambda: self._emit(self.key_back),
            )
            self._update_pin(
                self._right,
                now,
                on_short=lambda: self._emit(self.key_down),
                on_hold=lambda: self._emit(self.key_select),
            )
            time.sleep(POLL_S)


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
