# Encoder — Adafruit Seesaw Rotary Encoder (Product 5880)

**Hardware Revision D**  
**Interface:** I²C Seesaw  
**Role:** Primary navigation device for the local display UI

---

## Part

| Field | Value |
|-------|-------|
| Product | Adafruit I2C STEMMA QT Rotary Encoder Breakout |
| Product ID | **5880** |
| Default I²C address | `0x36` (jumpers allow `0x36`–`0x3D`) |
| Logic / power | **3.3 V** (MineBox rail) |
| On-module switch GPIO | Seesaw pin **24** (active-low) |

---

## Wiring (breakout → Pi)

| Encoder pad | MineBox / Pi | Notes |
|-------------|--------------|-------|
| VIN | 3.3 V | Do not use 5 V on a 3.3 V-only MineBox rail |
| GND | GND | |
| SDA | I²C1 SDA (BCM 2 / phys 3) | Bus `i2c_bus = 1` |
| SCL | I²C1 SCL (BCM 3 / phys 5) | |
| INT | BCM **24** (configurable) | Active-low interrupt; optional but recommended |
| 3Vo | — | Do not power the Pi from 3Vo |

STEMMA QT cables are supported when the panel exposes a QT connector.

---

## Software driver

- Module: `app/hardware/seesaw_encoder.py`
- Preferred stack: CircuitPython **Blinka** + `adafruit_seesaw` when installed
- Fallback stack: **`smbus2`** register access (declared in `requirements.txt`)
- Integrated by: `RaspberryPi5Hardware` (`app/hardware/pi5.py`)

Capabilities:

- Initialize / probe Seesaw
- Read rotation delta (CW positive, CCW negative)
- Read push-button (active-low)
- Optional INT GPIO
- Auto-reconnect after disconnect (never blocks boot)

---

## Configuration

See `[encoder]` in `config/hardware.example.toml` / `/etc/minebox/hardware.toml`:

```toml
[encoder]
enabled = true
type = "adafruit_seesaw"
status = "OK"
i2c_bus = 1
address = 0x36
interrupt_gpio = 24
rotation_step = 1
debounce_ms = 15
long_press_ms = 700
```

---

## Events

| Event | Meaning |
|-------|---------|
| `ENCODER_CW` | Rotate clockwise → selection down / next |
| `ENCODER_CCW` | Rotate counter-clockwise → selection up / prev |
| `ENCODER_PRESS` | Knob click → select |
| `ENCODER_LONG_PRESS` | Knob hold (secondary; defaults to back) |
| `ENCODER_DISCONNECTED` | Device lost |
| `ENCODER_RECONNECTED` | Device returned |

Legacy aliases `ENCODER_RIGHT` / `ENCODER_LEFT` remain accepted by ActionMap / keyboard helpers.

---

## Missing encoder / first boot

If the encoder is absent or I²C fails:

1. Log a warning
2. Emit / treat as disconnected
3. Fall back to **two-button navigation**
4. **Never prevent boot** (`health().ok` stays true)

---

## Mock / CI

`MockHardware` supports:

- `inject_encoder_delta(+/-n)`
- `set_encoder_press(bool)`
- `disconnect_encoder()` / `reconnect_encoder()`

---

## Verification

Automated: `tests/test_encoder_rev_d.py`  
On-device: Hardware diagnostics screen + physical CW/CCW/press checks.
