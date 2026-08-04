# Factory Reset — Prototype v1.0

## Endpoint

`POST /api/v1/first-boot/factory-reset`

Requires authentication (or a local recovery token) and `confirm=true`. Rate limited.

## Default behavior (preserves user data)

Clears:

- administrator credentials
- session / first-boot completion flags
- hotspot PSK and RCON secret from runtime secrets (forces re-rotation)
- nonessential wizard preferences

Preserves:

- Minecraft worlds
- backups
- server files under `/opt/minecraft` (unless erase requested)

## Full erase

Set `erase_worlds=true` and `confirm_erase_phrase` exactly `ERASE WORLDS`.

## Authorization

Provide either:

- `admin_password` matching the current administrator, or
- `recovery_token` from `/var/lib/minebox/recovery_token` (issued after reset; also used for local-console recovery)

No universal backdoor password.

## After reset

Appliance returns to setup-incomplete gating. Owner completes `/auth/setup` → `/setup` → `/first-boot` again.
