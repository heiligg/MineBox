#!/usr/bin/env python3
"""Physical MineBox buttons → curses key codes.

minebox-api is the sole GPIO owner (display HAL / bridge). This module must
never claim BCM lines — doing so races the API and yields "GPIO busy" on both.

Instead we poll http://127.0.0.1:8080/api/v1/display/events and map events to
curses keys (same intents as the graphical kiosk).

Encoder disabled / missing (current appliance default):
  Short Left/Right → KEY_UP / KEY_DOWN (nav)
  Hold Left/Right  → KEY_LEFT / KEY_ENTER (back / select)

Encoder present + enabled (Hardware Rev D):
  Short Left  → KEY_LEFT   (Back)
  Hold Left   → KEY_HOME   (Home / dashboard)
  Short Right → KEY_RIGHT  (Context / quick)
  Hold Right  → KEY_END    (Power menu)
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request

LOGGER = logging.getLogger("minebox.gpio_buttons")

_DEFAULT_EVENTS_URL = "http://127.0.0.1:8080/api/v1/display/events"
_POLL_S = 0.08


def _events_url() -> str:
    import os

    return os.environ.get("MINEBOX_DISPLAY_EVENTS_URL", _DEFAULT_EVENTS_URL).strip() or _DEFAULT_EVENTS_URL


def _encoder_enabled_in_config() -> bool:
    try:
        from core.minebox_config import get_config

        return bool(get_config().hardware.encoder_enabled)
    except Exception:  # noqa: BLE001
        return False


class ButtonController:
    """Background poller: API display events → curses key codes."""

    def __init__(
        self,
        *,
        key_up: int,
        key_down: int,
        key_back: int,
        key_select: int,
        key_home: int | None = None,
        key_context: int | None = None,
        key_power: int | None = None,
        rev_d: bool | None = None,
    ) -> None:
        self.key_up = key_up
        self.key_down = key_down
        self.key_back = key_back
        self.key_select = key_select
        self.key_home = key_home if key_home is not None else key_back
        self.key_context = key_context if key_context is not None else key_up
        self.key_power = key_power if key_power is not None else key_select
        self.rev_d = bool(rev_d) if rev_d is not None else _encoder_enabled_in_config()
        self._queue: queue.Queue[int] = queue.Queue(maxsize=32)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.available = False
        self._source = "api"
        self.left_gpio = 17
        self.right_gpio = 27

    def start(self) -> bool:
        if self._thread is not None:
            return self.available

        self.available = True
        self._thread = threading.Thread(
            target=self._run,
            name="minebox-gpio-buttons",
            daemon=True,
        )
        self._thread.start()
        mode = "Rev D secondary" if self.rev_d else "two-button nav"
        LOGGER.info(
            "Buttons via %s (%s); GPIO owned by minebox-api",
            self._source,
            mode,
        )
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
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

    def _key_for_event(self, event_type: str, scheme: str) -> int | None:
        rev_d = self.rev_d or scheme == "hardware_rev_d"
        mapping_two = {
            "LEFT_BUTTON_PRESS": self.key_up,
            "LEFT_BUTTON_HOLD": self.key_back,
            "RIGHT_BUTTON_PRESS": self.key_down,
            "RIGHT_BUTTON_HOLD": self.key_select,
            "ENCODER_CW": self.key_down,
            "ENCODER_RIGHT": self.key_down,
            "ENCODER_CCW": self.key_up,
            "ENCODER_LEFT": self.key_up,
            "ENCODER_PRESS": self.key_select,
            "ENCODER_LONG_PRESS": self.key_back,
        }
        mapping_rev_d = {
            "LEFT_BUTTON_PRESS": self.key_back,
            "LEFT_BUTTON_HOLD": self.key_home,
            "RIGHT_BUTTON_PRESS": self.key_context,
            "RIGHT_BUTTON_HOLD": self.key_power,
            "ENCODER_CW": self.key_down,
            "ENCODER_RIGHT": self.key_down,
            "ENCODER_CCW": self.key_up,
            "ENCODER_LEFT": self.key_up,
            "ENCODER_PRESS": self.key_select,
            "ENCODER_LONG_PRESS": self.key_back,
        }
        table = mapping_rev_d if rev_d else mapping_two
        return table.get(event_type)

    def _fetch_events(self) -> tuple[list[dict], str]:
        req = urllib.request.Request(
            _events_url(),
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            body = resp.read().decode("utf-8", "replace")
        data = json.loads(body) if body else {}
        events = data.get("events") or []
        scheme = str((data.get("map") or {}).get("scheme") or "")
        if not isinstance(events, list):
            events = []
        return events, scheme

    def _run(self) -> None:
        failures = 0
        while not self._stop.is_set():
            try:
                events, scheme = self._fetch_events()
                failures = 0
                if scheme == "hardware_rev_d":
                    self.rev_d = True
                elif scheme == "two_button_fallback":
                    self.rev_d = False
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    event_type = str(ev.get("type") or "")
                    key = self._key_for_event(event_type, scheme)
                    if key is not None:
                        self._emit(key)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                failures += 1
                if failures in {1, 20, 100}:
                    LOGGER.warning("Display events poll failed (%s): %s", failures, exc)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                if failures in {1, 20, 100}:
                    LOGGER.warning("Display events poll error (%s): %s", failures, exc)
            time.sleep(_POLL_S)


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


LEFT_GPIO = 17
RIGHT_GPIO = 27
