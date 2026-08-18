# MineBox Hardware Pinout — Prototype v1.0 (Hardware Rev D)

**Status:** Buttons, encoder I²C, and INT verified from the panel JST mapping  
**Date:** 2026-08-17  
**Rule:** Software uses **BCM GPIO numbers**, not 40-pin header numbers. Power pins are not GPIOs. Do not invent LED or fan GPIO assignments.

---

## Verification legend

| Tag | Meaning |
|-----|---------|
| `UNVERIFIED_AGAINST_PCB` | Present in software/config only; electrical pinout not yet in repo |
| `NOT_CONFIGURED` | Feature exists in HAL but pins intentionally unset |
| `SOURCE_VERIFIED` | Confirmed against the assembled panel / J1 mapping |
| `PRODUCT_DATASHEET` | Taken from Adafruit Product 5880 documentation |

---

## Buttons

Active-low (pressed = 0). 10 k pull-up on the PCB.

| Function | J1 hole | Header pin | BCM GPIO | Notes | Verification |
|----------|---------|------------|----------|-------|--------------|
| Left button (SW1) | 4 | 11 | **GPIO17** | Active low | SOURCE_VERIFIED |
| Right button (SW2) | 5 | 13 | **GPIO27** | Active low | SOURCE_VERIFIED |

Centralized config: `/etc/minebox/hardware.toml` (example: `config/hardware.example.toml`).

```
BTN_LEFT  = 17    # GPIO17, active low
BTN_RIGHT = 27    # GPIO27, active low
```

**Current software (encoder disabled / missing):**

| Input | Short press | Long press |
|-------|-------------|------------|
| Left | `prev` (move up) | `back` |
| Right | `next` (move down) | `select` |

When the Seesaw encoder is enabled and connected, buttons switch to secondary Rev D actions (back/home/context/power).

Timing defaults: debounce 40 ms, long-press 450 ms, lockout 150 ms.

`minebox-api` is the **sole GPIO owner** for the buttons (`SupplementaryGroups=gpio input`).
The curses recovery UI (`minebox-ui`) must poll `/api/v1/display/events` and must not
open gpiozero on the same BCM lines — dual claim causes `GPIO busy` and dead buttons.

Do not add `DeviceAllow=` for specific gpiochips — that closes the device policy and can hide the chip
gpiozero/lgpio needs on some Pi 5 kernels.
---

## Encoder (Adafruit 5880 — Seesaw I²C)

Bus: **I²C1** (`/dev/i2c-1`). Address: **0x36**. Enable: `dtparam=i2c_arm=on`.

SDA/SCL are clock on J1-6 / GPIO3 and data on J1-7 / GPIO2. Do **not** assume SDA-then-SCL order on the JST.

| Function | J1 hole | Header pin | BCM GPIO | Notes | Verification |
|----------|---------|------------|----------|-------|--------------|
| Encoder SDA | 7 | 3 | **GPIO2** | I2C1 data | SOURCE_VERIFIED |
| Encoder SCL | 6 | 5 | **GPIO3** | I2C1 clock | SOURCE_VERIFIED |
| Encoder INT | 8 | 15 | **GPIO22** | Optional, open-drain | SOURCE_VERIFIED |
| Push switch | — | — | Seesaw GPIO 24 | On-module, active-low | PRODUCT_DATASHEET |

```
ENC_INT   = 22    # GPIO22, optional
I2C_BUS   = 1
ENC_ADDR  = 0x36
```

There are **no** quadrature `gpio_a` / `gpio_b` BCM pins — rotation is tracked on-module.

HAL: `app/hardware/seesaw_encoder.py` via `RaspberryPi5Hardware`.  
Details: `docs/v1/Encoder.md`.

---

## Power (not software pins)

Header pins **2** and **6** stay with the screen. Same 5 V and ground rails inside the Pi.

| Rail | J1 | Header pin used | Why |
|------|----|-----------------|-----|
| 3.3 V | 1 | 1 | Encoder + pull-ups |
| 5 V (LEDs only) | 3 | **4** | Pin 2 taken by the screen |
| GND | 2 | **9** | Pin 6 taken by the screen |

Do not treat 3.3 V / 5 V / GND as GPIOs.

---

## Illuminated button LEDs

| Signal | BCM | Status |
|--------|-----|--------|
| Left LED | — | **NOT_CONFIGURED** |
| Right LED | — | **NOT_CONFIGURED** |

---

## Fan / PWM

| Signal | BCM | Status |
|--------|-----|--------|
| Fan GPIO/PWM | — | **NOT_CONFIGURED** |

Pi 5 profile may report platform cooling as degraded/auto without claiming PCB GPIO control.

---

## Conflicts

- Older software used GPIO23 (left) and GPIO17 (right) with INT on GPIO24. Current mapping is GPIO17 / GPIO27 / INT GPIO22.
- Rev D replaces temporary two-button *navigation* with the Seesaw encoder; buttons remain as secondary controls.

---

## Owner action required

LED and fan GPIO still need electrical pinout before they can be configured.
