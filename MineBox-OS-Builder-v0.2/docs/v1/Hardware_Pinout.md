# MineBox Hardware Pinout — Prototype v1.0 (Hardware Rev D)

**Status:** Partial — button GPIOs provisional; encoder is I²C Seesaw (Product 5880)  
**Date:** 2026-08-05  
**Rule:** Do not invent quadrature encoder GPIO, LED, or fan GPIO assignments.

---

## Verification legend

| Tag | Meaning |
|-----|---------|
| `UNVERIFIED_AGAINST_PCB` | Present in software/config only; electrical pinout not yet in repo |
| `NOT_CONFIGURED` | Feature exists in HAL but pins intentionally unset |
| `SOURCE_VERIFIED` | Confirmed against PCB / KiCad in this repository (none yet) |
| `PRODUCT_DATASHEET` | Taken from Adafruit Product 5880 documentation |

---

## Buttons (provisional)

| Signal | Raspberry Pi BCM | Physical pin | Voltage | Direction | Pull | Active | Source | Verification |
|--------|------------------|--------------|---------|-----------|------|--------|--------|--------------|
| Left button | 23 | 16 | 3.3 V logic | Input | Internal pull-up | Active-low (to GND) | `config/hardware.example.toml` | **UNVERIFIED_AGAINST_PCB** |
| Right button | 17 | 11 | 3.3 V logic | Input | Internal pull-up | Active-low (to GND) | same | **UNVERIFIED_AGAINST_PCB** |
| GND | — | 14 (or any GND) | 0 V | — | — | — | — | UNVERIFIED_AGAINST_PCB |

Centralized config: `/etc/minebox/hardware.toml` (example: `config/hardware.example.toml`).

Wire each switch between the BCM pin and **GND** (active-low). Do not connect button inputs to 5 V.

**Current software (encoder disabled):**

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

| Signal | Connection | Notes | Verification |
|--------|------------|-------|--------------|
| VIN | 3.3 V | MineBox power rail | PRODUCT_DATASHEET |
| GND | GND | | PRODUCT_DATASHEET |
| SDA | I²C1 SDA (BCM 2) | `i2c_bus = 1` | PRODUCT_DATASHEET |
| SCL | I²C1 SCL (BCM 3) | | PRODUCT_DATASHEET |
| INT | BCM **24** | Optional; `interrupt_gpio` in config | UNVERIFIED_AGAINST_PCB (Pi pin choice) |
| 3Vo | unused | Do not back-power | PRODUCT_DATASHEET |
| Push switch | Internal Seesaw GPIO 24 | Active-low | PRODUCT_DATASHEET |
| I²C address | `0x36` default | Jumpers `0x36`–`0x3D` | PRODUCT_DATASHEET |

There are **no** quadrature `gpio_a` / `gpio_b` BCM pins — rotation is tracked on-module.

HAL: `app/hardware/seesaw_encoder.py` via `RaspberryPi5Hardware`.  
Details: `docs/v1/Encoder.md`.

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

- Historical ROADMAP deferred buttons while app code used BCM23/17 — still provisional.
- Rev D replaces temporary two-button *navigation* with the Seesaw encoder; buttons remain as secondary controls.

---

## Owner action required

Add electrical pinout (PCB or KiCad export) for INT routing, LEDs, and fan; then flip verification to `SOURCE_VERIFIED` where applicable.
