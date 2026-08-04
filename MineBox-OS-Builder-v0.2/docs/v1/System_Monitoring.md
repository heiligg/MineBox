# System Monitoring — Prototype v1.0

## Sources

- `services/monitoring.py` — CPU%, memory%, disk, uptime, fan RPM/PWM discovery, alerts
- `services/thermal.py` — thermal state machine with hysteresis
- HAL — temperature / throttling / fan capability
- `StateService.system_health()` — aggregated for foundation status

## Exposed fields

CPU temperature, CPU load, memory used/total (via percent helpers), disk, uptime, throttling (`vcgencmd` when present), fan capability/state, thermal health.

## APIs

- `GET /api/v1/system`
- `GET /api/v1/status`
- `GET /api/v1/status/foundation`
- `GET /api/v1/status/thermal`
- `GET /api/v1/system/thermal`

Fan GPIO control remains `NOT_CONFIGURED`; platform cooling may still report `AUTO`.
