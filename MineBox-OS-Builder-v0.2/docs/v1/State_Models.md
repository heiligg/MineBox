# MineBox State Models — Prototype v1.0

## Minecraft states

| State | Meaning |
|-------|---------|
| `NOT_INSTALLED` | No server instance |
| `INSTALLING` | Create/download in progress |
| `STOPPED` | Installed, not running |
| `STARTING` | Start requested / coming up |
| `RUNNING` | Healthy (not PID alone) |
| `STOPPING` | Graceful stop in progress |
| `BACKING_UP` | Backup operation |
| `UPDATING` | Server/software update |
| `ERROR` | Failed / unhealthy |
| `CRASHED` | Unexpected exit |

Implementation: `app/core/states.py` (`MinecraftState`, `MinecraftStateMachine`, `resolve_minecraft_state`).

### Health evidence

RUNNING requires `process_present` or `service_active` **and** (`rcon_responsive` or `port_listening`).

A process/service that is up without port/RCON evidence resolves to `ERROR` with reason noting that PID alone is not RUNNING.

Each state record includes: `value`, `reason`, `since`, `last_error`, `health`.

### Transitions

Invalid transitions raise / return errors (e.g. `NOT_INSTALLED → RUNNING`). See unit tests in `tests/test_states.py`.

## System / network / hardware

| Domain | Values (summary) |
|--------|------------------|
| System health | `UNKNOWN`, `HEALTHY`, `DEGRADED`, `CRITICAL` (temperature thresholds from hardware config) |
| Network (placeholder CP2) | SoftAP summary only; full model in Checkpoint 6 |
| Hardware features | `OK`, `NOT_CONFIGURED`, `UNSUPPORTED`, `UNAVAILABLE`, `DEGRADED` |

## Shared backend status

`core.state_service.StateService.public_status()` aggregates setup, Minecraft, system, hardware, providers, and network placeholder for web + future display UIs via `/api/v1/status/foundation`.
