# MineBox Hardware Pinout — Prototype v1.0

**Status:** Partial — button GPIOs are **provisional**  
**Date:** 2026-08-01  
**Rule:** Do not invent encoder, LED, or fan GPIO assignments.

---

## Verification legend

| Tag | Meaning |
|-----|---------|
| `UNVERIFIED_AGAINST_PCB` | Present in software/config only; electrical pinout not yet in repo |
| `NOT_CONFIGURED` | Feature exists in HAL but pins intentionally unset |
| `SOURCE_VERIFIED` | Confirmed against PCB / KiCad in this repository (none yet) |

---

## Buttons (provisional)

| Signal | Raspberry Pi BCM | Physical pin | Voltage | Direction | Pull | Active | Source | Verification |
|--------|------------------|--------------|---------|-----------|------|--------|--------|--------------|
| Left button | 23 | 16 | 3.3 V logic | Input | Internal pull-up | Active-low (to GND) | `config/hardware.example.toml`, former `gpio_buttons.py` defaults, `app/README.md` | **UNVERIFIED_AGAINST_PCB** |
| Right button | 17 | 11 | 3.3 V logic | Input | Internal pull-up | Active-low (to GND) | same | **UNVERIFIED_AGAINST_PCB** |
| GND | — | 14 | 0 V | — | — | — | `app/README.md` | UNVERIFIED_AGAINST_PCB |

Centralized config: `/etc/minebox/hardware.toml` (example: `config/hardware.example.toml`).

Default software behavior (configurable):

| Input | Short press | Long press |
|-------|-------------|------------|
| Left | `nav_previous` | `back` |
| Right | `nav_next` | `confirm` |

Timing defaults: debounce 40 ms, long-press 450 ms, lockout 150 ms.

---

## Encoder (Adafruit 5880)

| Signal | BCM | Connector | Status |
|--------|-----|-----------|--------|
| A / B / Switch | — | — | **NOT_CONFIGURED** — no PCB pinout in repository |

HAL returns `NOT_CONFIGURED` / zero rotation. Do not invent pins.

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

Pi 5 profile may report platform cooling (`FAN_PWM` / firmware) as degraded/auto without claiming PCB GPIO control.

---

## Conflicts

- `docs/ROADMAP.md` historically listed button GPIOs as hardware-deferred while application code used BCM23/17. **Resolved for software** by owner decision: treat BCM23/17 as provisional current mappings in centralized config with `UNVERIFIED_AGAINST_PCB`.
- No KiCad / front-panel PCB files are present in this repository at Checkpoint 2.

---

## Owner action required

Add electrical pinout (PCB or KiCad export) for encoder, LEDs, and fan; then update `hardware.toml` and flip verification to `SOURCE_VERIFIED`.
