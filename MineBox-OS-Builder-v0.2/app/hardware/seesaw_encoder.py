"""Adafruit Seesaw rotary encoder (Product 5880) over I²C.

Prefers CircuitPython Blinka + adafruit_seesaw when available; otherwise
uses smbus2 register access. Missing hardware never raises out of poll —
callers treat disconnected as zero delta / not pressed and reconnect.
"""

from __future__ import annotations

import logging
import struct
import threading
import time
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger("minebox.hardware.seesaw_encoder")

# Seesaw register map (Adafruit seesaw encoder firmware).
_STATUS_BASE = 0x00
_STATUS_HW_ID = 0x01
_STATUS_VERSION = 0x02
_STATUS_SWRST = 0x7F

_GPIO_BASE = 0x01
_GPIO_DIRCLR_BULK = 0x03
_GPIO_PULLENSET = 0x0B
_GPIO_BULK = 0x04
_GPIO_INTENSET = 0x08

_ENCODER_BASE = 0x11
_ENCODER_INTENSET = 0x10
_ENCODER_DELTA = 0x40

# Product 5880 push switch on Seesaw GPIO 24 (active-low).
_SS_SWITCH_PIN = 24
_DEFAULT_ADDR = 0x36
_RECONNECT_INTERVAL_S = 2.0
_RECONNECT_BACKOFF_MAX_S = 60.0
_FULL_SCAN_INTERVAL_S = 300.0


@dataclass
class SeesawEncoderConfig:
    i2c_bus: int = 1
    address: int = _DEFAULT_ADDR
    interrupt_gpio: int | None = 24
    rotation_step: int = 1
    debounce_ms: int = 15
    long_press_ms: int = 700
    reconnect_interval_s: float = _RECONNECT_INTERVAL_S


class SeesawEncoderDriver:
    """Thread-safe Seesaw encoder reader with auto-reconnect.

    Missing hardware must never block the MineBox API. Reconnect uses
    exponential backoff and avoids scanning the full address range on every
    attempt (I²C NACKs are slow and were starving uvicorn).
    """

    def __init__(self, config: SeesawEncoderConfig | None = None) -> None:
        self.config = config or SeesawEncoderConfig()
        self._lock = threading.RLock()
        self._connected = False
        self._backend: str | None = None
        self._bus: Any = None
        self._seesaw: Any = None
        self._last_error: str | None = None
        self._last_connect_attempt = 0.0
        self._backoff_s = float(self.config.reconnect_interval_s)
        self._last_full_scan = 0.0
        self._pending_delta = 0
        self._press = False
        self._int_btn = None
        self._ever_connected = False
        self._connecting = False
        # Never block the API process on a missing encoder at import/start.
        self._schedule_connect()

    def _schedule_connect(self) -> None:
        with self._lock:
            if self._connected or self._connecting:
                return
            self._connecting = True
            self._last_connect_attempt = time.monotonic()

        def worker() -> None:
            try:
                self.connect()
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("Seesaw connect worker failed: %s", exc)
            finally:
                with self._lock:
                    self._connecting = False

        threading.Thread(
            target=worker,
            name="minebox-seesaw-connect",
            daemon=True,
        ).start()

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def backend(self) -> str | None:
        with self._lock:
            return self._backend

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    @property
    def ever_connected(self) -> bool:
        with self._lock:
            return self._ever_connected

    def connect(self) -> bool:
        with self._lock:
            self._last_connect_attempt = time.monotonic()
            self.close_unlocked()
            ok = False
            if self._try_blinka():
                ok = True
            elif self._try_smbus():
                ok = True
            if ok:
                self._backoff_s = float(self.config.reconnect_interval_s)
            else:
                self._backoff_s = min(
                    _RECONNECT_BACKOFF_MAX_S,
                    max(self._backoff_s * 2.0, float(self.config.reconnect_interval_s)),
                )
            return ok

    def close(self) -> None:
        with self._lock:
            self.close_unlocked()

    def close_unlocked(self) -> None:
        if self._int_btn is not None:
            try:
                self._int_btn.close()
            except Exception:  # noqa: BLE001
                pass
            self._int_btn = None
        if self._seesaw is not None:
            self._seesaw = None
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:  # noqa: BLE001
                pass
            self._bus = None
        self._connected = False
        self._backend = None

    def _address_candidates(self) -> list[int]:
        """Configured address first; full 0x36-0x3D scan only periodically."""
        primary = int(self.config.address)
        now = time.monotonic()
        do_full = (now - self._last_full_scan) >= _FULL_SCAN_INTERVAL_S
        if not do_full and self._last_full_scan > 0:
            return [primary]
        self._last_full_scan = now
        addrs = [primary]
        for candidate in range(0x36, 0x3E):
            if candidate not in addrs:
                addrs.append(candidate)
        return addrs

    def _try_blinka(self) -> bool:
        try:
            import board  # type: ignore
            import busio  # type: ignore
            from adafruit_seesaw import digitalio as ss_digitalio  # type: ignore
            from adafruit_seesaw import rotaryio  # type: ignore
            from adafruit_seesaw.seesaw import Seesaw  # type: ignore
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Blinka/seesaw unavailable: %s", exc)
            return False

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            ss = Seesaw(i2c, addr=self.config.address)
            button = ss_digitalio.DigitalIO(ss, _SS_SWITCH_PIN)
            button.switch_to_input(ss_digitalio.Pull.UP)  # type: ignore[attr-defined]
            encoder = rotaryio.IncrementalEncoder(ss)
            try:
                ss.pin_mode(_SS_SWITCH_PIN, Seesaw.INPUT_PULLUP)
                ss.set_GPIO_interrupts(1 << _SS_SWITCH_PIN, True)
                ss.enable_encoder_interrupt()
            except Exception:  # noqa: BLE001
                pass
            self._seesaw = {"ss": ss, "button": button, "encoder": encoder, "last_pos": int(encoder.position)}
            self._backend = "blinka"
            self._connected = True
            self._ever_connected = True
            self._last_error = None
            self._setup_interrupt_gpio()
            LOGGER.info(
                "Seesaw encoder connected via Blinka at 0x%02X on bus hint %s",
                self.config.address,
                self.config.i2c_bus,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"Blinka Seesaw init failed: {exc}"
            LOGGER.warning(self._last_error)
            self.close_unlocked()
            return False

    def _try_smbus(self) -> bool:
        try:
            from smbus2 import SMBus
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"smbus2 unavailable: {exc}"
            LOGGER.debug(self._last_error)
            return False

        try:
            addrs = self._address_candidates()
            bus = SMBus(self.config.i2c_bus)
            hw_id = None
            used_addr = self.config.address
            for addr in addrs:
                self.config.address = addr
                hw_id = self._smbus_read8(bus, _STATUS_BASE, _STATUS_HW_ID)
                if hw_id is not None:
                    used_addr = addr
                    break
            if hw_id is None:
                self.config.address = used_addr
                raise OSError(
                    f"no response to Seesaw HW_ID "
                    f"(probed {[hex(a) for a in addrs]}) bus={self.config.i2c_bus}"
                )
            self.config.address = used_addr
            # Soft reset then configure switch pull-up + encoder IRQ.
            self._smbus_write(bus, _STATUS_BASE, _STATUS_SWRST, bytes([0xFF]))
            time.sleep(0.02)
            pin_mask = struct.pack(">I", 1 << _SS_SWITCH_PIN)
            self._smbus_write(bus, _GPIO_BASE, _GPIO_DIRCLR_BULK, pin_mask)
            self._smbus_write(bus, _GPIO_BASE, _GPIO_PULLENSET, pin_mask)
            # Set pull-up high via bulk set after pull enable (bulk write 1).
            self._smbus_write(bus, _GPIO_BASE, 0x05, pin_mask)  # SET bulk
            self._smbus_write(bus, _GPIO_BASE, _GPIO_INTENSET, pin_mask)
            self._smbus_write(bus, _ENCODER_BASE, _ENCODER_INTENSET, bytes([0x01]))
            # Drain delta.
            self._smbus_read_delta(bus)
            self._bus = bus
            self._backend = "smbus2"
            self._connected = True
            self._ever_connected = True
            self._last_error = None
            self._setup_interrupt_gpio()
            LOGGER.info(
                "Seesaw encoder connected via smbus2 bus=%s addr=0x%02X hw_id=0x%02X",
                self.config.i2c_bus,
                self.config.address,
                hw_id,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"smbus2 Seesaw init failed: {exc}"
            # Avoid flooding the journal / starving the API when the encoder is absent.
            if self._backoff_s <= float(self.config.reconnect_interval_s) * 2:
                LOGGER.warning(self._last_error)
            else:
                LOGGER.debug(self._last_error)
            try:
                if "bus" in locals():
                    bus.close()
            except Exception:  # noqa: BLE001
                pass
            self.close_unlocked()
            return False

    def _setup_interrupt_gpio(self) -> None:
        gpio = self.config.interrupt_gpio
        if gpio is None:
            return
        try:
            from gpiozero import Button

            # INT is open-drain active-low from Seesaw.
            self._int_btn = Button(gpio, pull_up=True, bounce_time=None)
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Encoder INT GPIO %s unavailable: %s", gpio, exc)
            self._int_btn = None

    def _maybe_reconnect(self) -> None:
        """Kick a background reconnect; never block the dashboard request path."""
        with self._lock:
            if self._connected or self._connecting:
                return
            now = time.monotonic()
            if (now - self._last_connect_attempt) < self._backoff_s:
                return
        self._schedule_connect()

    def poll(self) -> tuple[int, bool]:
        """Read rotation delta (signed steps) and pressed state. Safe if missing."""
        self._maybe_reconnect()
        with self._lock:
            if not self._connected:
                return 0, False
            try:
                if self._backend == "blinka":
                    delta, pressed = self._poll_blinka()
                else:
                    delta, pressed = self._poll_smbus()
                step = max(1, int(self.config.rotation_step))
                self._pending_delta += int(delta)
                steps = int(self._pending_delta // step)
                self._pending_delta -= steps * step
                self._press = pressed
                return steps, bool(pressed)
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"Seesaw poll failed: {exc}"
                LOGGER.warning(self._last_error)
                self.close_unlocked()
                return 0, False

    def read_delta(self) -> int:
        delta, _ = self.poll()
        return delta

    def read_press(self) -> bool:
        # Prefer last poll cache; also allow direct read.
        self._maybe_reconnect()
        with self._lock:
            if not self._connected:
                return False
            try:
                if self._backend == "blinka":
                    _, pressed = self._poll_blinka(consume_delta=False)
                else:
                    pressed = self._smbus_read_switch(self._bus)
                self._press = pressed
                return pressed
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"Seesaw press read failed: {exc}"
                self.close_unlocked()
                return False

    @property
    def cached_press(self) -> bool:
        with self._lock:
            return bool(self._press)

    def _poll_blinka(self, *, consume_delta: bool = True) -> tuple[int, bool]:
        assert self._seesaw is not None
        enc = self._seesaw["encoder"]
        button = self._seesaw["button"]
        pos = int(enc.position)
        last = int(self._seesaw["last_pos"])
        delta = (pos - last) if consume_delta else 0
        if consume_delta:
            self._seesaw["last_pos"] = pos
        # Active-low switch.
        pressed = not bool(button.value)
        return delta, pressed

    def _poll_smbus(self) -> tuple[int, bool]:
        assert self._bus is not None
        delta = self._smbus_read_delta(self._bus)
        pressed = self._smbus_read_switch(self._bus)
        return delta, pressed

    def _smbus_write(self, bus: Any, reg_base: int, reg: int, payload: bytes) -> None:
        bus.write_i2c_block_data(self.config.address, reg_base, [reg, *payload])

    def _smbus_read(self, bus: Any, reg_base: int, reg: int, length: int) -> bytes:
        from smbus2 import i2c_msg

        write = i2c_msg.write(self.config.address, bytes([reg_base, reg]))
        bus.i2c_rdwr(write)
        time.sleep(0.001)
        read = i2c_msg.read(self.config.address, length)
        bus.i2c_rdwr(read)
        return bytes(read)

    def _smbus_read8(self, bus: Any, reg_base: int, reg: int) -> int | None:
        try:
            data = self._smbus_read(bus, reg_base, reg, 1)
            return data[0]
        except Exception:  # noqa: BLE001
            return None

    def _smbus_read_delta(self, bus: Any) -> int:
        raw = self._smbus_read(bus, _ENCODER_BASE, _ENCODER_DELTA, 4)
        return int(struct.unpack(">i", raw)[0])

    def _smbus_read_switch(self, bus: Any) -> bool:
        raw = self._smbus_read(bus, _GPIO_BASE, _GPIO_BULK, 4)
        value = struct.unpack(">I", raw)[0]
        # Active-low: pressed when bit clear.
        return (value & (1 << _SS_SWITCH_PIN)) == 0

    def diagnostic_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "type": "adafruit_seesaw",
                "product": 5880,
                "connected": self._connected,
                "ever_connected": self._ever_connected,
                "backend": self._backend,
                "i2c_bus": self.config.i2c_bus,
                "address": f"0x{self.config.address:02x}",
                "interrupt_gpio": self.config.interrupt_gpio,
                "rotation_step": self.config.rotation_step,
                "debounce_ms": self.config.debounce_ms,
                "long_press_ms": self.config.long_press_ms,
                "last_error": self._last_error,
                "press": self._press,
            }
