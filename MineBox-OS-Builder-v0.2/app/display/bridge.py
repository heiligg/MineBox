"""HAL → DisplayEvent bridge with debounce, ordering, and disconnect handling."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from display.events import DisplayEvent, DisplayEventType, now_ts
from hardware.debounce import DebounceConfig, DebouncedButtonLogic, PressAction


class DisplayEventBridge:
    """Polls a hardware profile and emits ordered DisplayEvents.

    UI components must not touch GPIO; they consume events from this bridge
    (or the display API that wraps it).
    """

    def __init__(
        self,
        hardware: Any | None = None,
        *,
        debounce_ms: int = 40,
        long_press_ms: int = 450,
        lockout_ms: int = 150,
        encoder_debounce_ms: int | None = None,
        encoder_long_press_ms: int | None = None,
        max_queue: int = 128,
    ) -> None:
        self._hardware = hardware
        self._lock = threading.RLock()
        self._queue: deque[DisplayEvent] = deque(maxlen=max_queue)
        self._seq = 0
        self._connected = True
        self._encoder_connected = True
        enc_debounce = encoder_debounce_ms if encoder_debounce_ms is not None else debounce_ms
        enc_long = encoder_long_press_ms if encoder_long_press_ms is not None else long_press_ms
        self._encoder_press_logic = DebouncedButtonLogic(
            DebounceConfig(
                debounce_s=enc_debounce / 1000.0,
                long_press_s=enc_long / 1000.0,
                lockout_s=lockout_ms / 1000.0,
            )
        )
        self._left_logic = DebouncedButtonLogic(
            DebounceConfig(
                debounce_s=debounce_ms / 1000.0,
                long_press_s=long_press_ms / 1000.0,
                lockout_s=lockout_ms / 1000.0,
            )
        )
        self._right_logic = DebouncedButtonLogic(
            DebounceConfig(
                debounce_s=debounce_ms / 1000.0,
                long_press_s=long_press_ms / 1000.0,
                lockout_s=lockout_ms / 1000.0,
            )
        )
        self._diagnostics_mode = False

    def set_hardware(self, hardware: Any | None) -> None:
        with self._lock:
            self._hardware = hardware

    def set_diagnostics_mode(self, enabled: bool) -> None:
        with self._lock:
            self._diagnostics_mode = bool(enabled)

    @property
    def diagnostics_mode(self) -> bool:
        with self._lock:
            return self._diagnostics_mode

    @property
    def encoder_connected(self) -> bool:
        with self._lock:
            return self._encoder_connected

    def _emit(self, event_type: DisplayEventType, *, source: str = "hal") -> None:
        self._seq += 1
        self._queue.append(
            DisplayEvent(
                type=event_type,
                timestamp=now_ts(),
                source=source,
                sequence=self._seq,
            )
        )

    def inject(self, event_type: DisplayEventType | str, *, source: str = "mock") -> DisplayEvent:
        """Test/dev injection — bypasses GPIO."""
        if isinstance(event_type, str):
            event_type = DisplayEventType(event_type)
        with self._lock:
            self._emit(event_type, source=source)
            return self._queue[-1]

    def mark_disconnected(self) -> None:
        with self._lock:
            if self._connected:
                self._connected = False
                self._emit(DisplayEventType.HARDWARE_DISCONNECTED, source="bridge")

    def mark_reconnected(self) -> None:
        with self._lock:
            if not self._connected:
                self._connected = True
                self._emit(DisplayEventType.HARDWARE_RECONNECTED, source="bridge")

    def mark_encoder_disconnected(self) -> None:
        with self._lock:
            if self._encoder_connected:
                self._encoder_connected = False
                self._emit(DisplayEventType.ENCODER_DISCONNECTED, source="bridge")

    def mark_encoder_reconnected(self) -> None:
        with self._lock:
            if not self._encoder_connected:
                self._encoder_connected = True
                self._emit(DisplayEventType.ENCODER_RECONNECTED, source="bridge")

    def _encoder_available(self, hw: Any) -> bool:
        getter = getattr(hw, "encoder_available", None)
        if callable(getter):
            try:
                return bool(getter())
            except Exception:
                return False
        # Mock without explicit flag: treat as available when enabled in config.
        cfg = getattr(hw, "config", None)
        if cfg is not None and getattr(cfg, "encoder_enabled", False):
            # Disconnected injection can flip mock flag.
            flag = getattr(hw, "_encoder_present", None)
            if flag is not None:
                return bool(flag)
            return True
        return False

    def poll(self) -> list[DisplayEvent]:
        """Read HAL once and return newly queued events."""
        with self._lock:
            hw = self._hardware
            if hw is None:
                self.mark_disconnected()
                return self.drain()

            try:
                if not self._connected:
                    self._connected = True
                    self._emit(DisplayEventType.HARDWARE_RECONNECTED, source="bridge")

                now = time.monotonic()
                enc_ok = self._encoder_available(hw)
                if enc_ok and not self._encoder_connected:
                    self._encoder_connected = True
                    self._emit(DisplayEventType.ENCODER_RECONNECTED, source="bridge")
                elif not enc_ok and self._encoder_connected:
                    self._encoder_connected = False
                    self._emit(DisplayEventType.ENCODER_DISCONNECTED, source="bridge")

                # Encoder rotation (consume-on-read). Positive = CW.
                try:
                    delta = int(hw.read_encoder_delta() or 0)
                except Exception:
                    delta = 0
                if delta > 0:
                    for _ in range(min(delta, 8)):
                        self._emit(DisplayEventType.ENCODER_CW)
                elif delta < 0:
                    for _ in range(min(-delta, 8)):
                        self._emit(DisplayEventType.ENCODER_CCW)

                # Encoder press → short/long via debounce.
                try:
                    enc_pressed = bool(hw.read_encoder_press()) if enc_ok else False
                except Exception:
                    enc_pressed = False
                enc_action = self._encoder_press_logic.update(enc_pressed, now)
                if enc_action is PressAction.SHORT:
                    self._emit(DisplayEventType.ENCODER_PRESS)
                elif enc_action is PressAction.LONG:
                    self._emit(DisplayEventType.ENCODER_LONG_PRESS)

                # Physical buttons (always polled — secondary or fallback nav).
                try:
                    left = bool(hw.read_left_button())
                except Exception:
                    left = False
                try:
                    right = bool(hw.read_right_button())
                except Exception:
                    right = False

                left_action = self._left_logic.update(left, now)
                right_action = self._right_logic.update(right, now)
                if left_action is PressAction.SHORT:
                    self._emit(DisplayEventType.LEFT_BUTTON_PRESS)
                elif left_action is PressAction.LONG:
                    self._emit(DisplayEventType.LEFT_BUTTON_HOLD)
                if right_action is PressAction.SHORT:
                    self._emit(DisplayEventType.RIGHT_BUTTON_PRESS)
                elif right_action is PressAction.LONG:
                    self._emit(DisplayEventType.RIGHT_BUTTON_HOLD)

            except Exception:
                self.mark_disconnected()

            return self.drain()

    def drain(self) -> list[DisplayEvent]:
        with self._lock:
            items = list(self._queue)
            self._queue.clear()
            return items

    def diagnostic_live(self) -> dict[str, Any]:
        hw = self._hardware
        if hw is None:
            return {"connected": False, "profile": None, "encoder_connected": False}
        try:
            snap = hw.diagnostic_snapshot()
        except Exception as exc:  # noqa: BLE001
            return {"connected": False, "error": str(exc), "encoder_connected": False}
        return {
            "connected": self._connected,
            "encoder_connected": self._encoder_connected,
            "diagnostics_mode": self._diagnostics_mode,
            "left_button": bool(getattr(hw, "read_left_button", lambda: False)()),
            "right_button": bool(getattr(hw, "read_right_button", lambda: False)()),
            "encoder_press": bool(getattr(hw, "read_encoder_press", lambda: False)()),
            "snapshot": snap,
        }


_BRIDGE: DisplayEventBridge | None = None


def get_display_bridge() -> DisplayEventBridge:
    global _BRIDGE
    if _BRIDGE is None:
        enc_debounce = 15
        enc_long = 700
        debounce = 40
        long_press = 450
        lockout = 150
        try:
            from core.minebox_config import get_config

            hw_cfg = get_config().hardware
            debounce = hw_cfg.debounce_ms
            long_press = hw_cfg.long_press_ms
            lockout = hw_cfg.lockout_ms
            enc_debounce = hw_cfg.encoder_debounce_ms
            enc_long = hw_cfg.encoder_long_press_ms
        except Exception:
            pass
        _BRIDGE = DisplayEventBridge(
            debounce_ms=debounce,
            long_press_ms=long_press,
            lockout_ms=lockout,
            encoder_debounce_ms=enc_debounce,
            encoder_long_press_ms=enc_long,
        )
        try:
            from hardware.factory import get_hardware

            _BRIDGE.set_hardware(get_hardware())
        except Exception:
            pass
    return _BRIDGE


def reset_display_bridge_for_tests() -> DisplayEventBridge:
    global _BRIDGE
    _BRIDGE = DisplayEventBridge()
    return _BRIDGE
