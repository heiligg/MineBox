# Minecraft Lifecycle — Prototype v1.0

## State machine

Implemented in `core/states.py`, driven by `services/lifecycle.py`.

States: `NOT_INSTALLED`, `INSTALLING`, `STOPPED`, `STARTING`, `RUNNING`, `STOPPING`, `BACKING_UP`, `UPDATING`, `ERROR`, `CRASHED`.

Runtime persistence: `/var/lib/minebox/minecraft_lifecycle.json` (override with `MINEBOX_RUNTIME_DIR`).

## Operations

| API | Behavior |
|-----|----------|
| `POST /api/v1/minecraft/start` | Lifecycle start → `start_service` → wait for health |
| `POST /api/v1/minecraft/stop` | Lifecycle stop → `stop_service` |
| `POST /api/v1/minecraft/restart` | Coordinated stop+start |
| `POST /api/v1/minecraft/recover` | `CRASHED`/`ERROR` → `STOPPED` → start |

Low-level helpers (no state machine): `minecraft.start_service()`, `stop_service()`, `restart_service()`.

## Health

`services/minecraft_health.py` collects evidence:

- systemd/process active
- game port listening
- RCON `list` success
- recent log mtime
- startup markers (`Done (`)

**RUNNING requires** port or RCON (or port + startup marker). PID alone is never enough.

Timeouts: `MINEBOX_MC_STARTUP_TIMEOUT` (default 180s), `MINEBOX_MC_SHUTDOWN_TIMEOUT` (default 60s).

## Conflicts

`services/operations.py` blocks conflicting long-running ops (backup vs restore, start vs restore, etc.).
