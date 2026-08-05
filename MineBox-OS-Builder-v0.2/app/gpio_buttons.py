#!/usr/bin/env python3
"""Physical MineBox buttons → curses key codes.

Hardware Rev D (encoder present):
  Short Left  → KEY_LEFT   (Back)
  Hold Left   → KEY_HOME   (Home / dashboard)
  Short Right → KEY_RIGHT  (Context / quick)
  Hold Right  → KEY_END    (Power menu)

Fallback when encoder missing:
  Short Left/Right → KEY_UP / KEY_DOWN (nav)
  Hold Left/Right  → KEY_LEFT / KEY_ENTER (back / select)

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
        from hardware.factory import get_hardware

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


class _DebouncedPin:
    def __init__(self, button, logic: DebouncedButtonLogic) -> None:
        self.button = button
        self.logic = logic

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

        self._left = _DebouncedPin(left_btn, DebouncedButtonLogic(self.debounce))
        self._right = _DebouncedPin(right_btn, DebouncedButtonLogic(self.debounce))
        self.available = True
        self._thread = threading.Thread(
            target=self._run,
            name="minebox-gpio-buttons",
            daemon=True,
        )
        self._thread.start()
        if self.rev_d:
            LOGGER.info(
                "Buttons Rev D (secondary): L short=back hold=home; "
                "R short=context hold=power (BCM %s/%s)",
                self.left_gpio,
                self.right_gpio,
            )
        else:
            LOGGER.info(
                "Buttons fallback nav (encoder missing): short L/R=nav, "
                "hold L=back, hold R=confirm (BCM %s/%s)",
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
        pin: _DebouncedPin,
        now: float,
        on_short: Callable[[], None],
        on_hold: Callable[[], None],
    ) -> None:
        raw = bool(pin.button.is_pressed)
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
