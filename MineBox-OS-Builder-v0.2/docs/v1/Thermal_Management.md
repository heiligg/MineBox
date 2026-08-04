# Thermal Management — Prototype v1.0

## States

`NORMAL` → `WARM` → `HOT` → `CRITICAL`, plus `SENSOR_UNAVAILABLE`.

Thresholds default from hardware config (`fan_off_below_c`, `fan_on_above_c`, `fan_critical_c`) with 3°C hysteresis on the way down.

## Fan control

| Mode | Behavior |
|------|----------|
| `NOT_CONFIGURED` | Temperature monitored; no GPIO fan claims |
| `platform` | Pi firmware cooler may be `AUTO` if detectable |
| `gpio` / `pwm` | Not enabled until PCB pinout is verified |

State **changes** are logged; every sample is not.

Module: `services/thermal.py`.
