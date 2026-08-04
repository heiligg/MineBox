# API Route Security Inventory — Prototype v1.0 (Checkpoint 4)

Classifications:

- **public-health** — always reachable
- **public-auth-entry** — login/setup/csrf/status
- **setup-public** — allowed while first-boot incomplete (and often after for status)
- **auth-read** — authenticated GET
- **auth-write** — authenticated mutation + CSRF
- **privileged/destructive** — auth + CSRF + confirm/rate-limit; blocked until setup complete

OpenAPI `/docs`, `/redoc`, `/api/v1/openapi.json` are **disabled** unless `MINEBOX_DEV_MODE=1` or `MINEBOX_ENABLE_DOCS=1`.  
No `CORSMiddleware` / no credentialed wildcard CORS.

## Always public

| Method | Path | Class |
|--------|------|-------|
| GET | `/health` | public-health |
| GET | `/api/v1/health` | public-health |
| GET | `/login` | public-auth-entry |
| GET/POST | `/auth/setup` | public-auth-entry (rate limited) |
| POST | `/auth/login` | public-auth-entry (rate limited) |
| GET | `/api/v1/auth/status` | public-auth-entry |
| GET | `/api/v1/auth/csrf` | public-auth-entry |
| GET | `/display`, `/display/dev` | public (kiosk shell; actions still gated) |
| GET | `/api/v1/display/snapshot`, `/events`, `/trust`, `/action-map` | public read for local UI |
| POST | `/api/v1/display/session` | loopback session cookie |
| GET | `/static/*` | public |

## Remote access (authenticated)

| Method | Path | Class |
|--------|------|-------|
| GET | `/api/v1/remote-access/status` | auth-read (Tailscale IPs only when authenticated) |
| POST | `/api/v1/remote-access/enable` | privileged (auth + CSRF + rate limit; key in body only) |
| POST | `/api/v1/remote-access/disable\|logout` | privileged (`confirm=true`) |
| POST | `/api/v1/remote-access/exposure` | auth-write |
| GET | `/api/v1/network/roles` | auth-read (setup-public while incomplete) |
| POST | `/api/v1/network/recovery/retry` | auth-write |
| GET | `/api/v1/network/support-bundle` | auth-read (redacted) |

## Local display (loopback token)

| Method | Path | Class |
|--------|------|-------|
| POST | `/api/v1/display/action` | loopback + display token; scoped actions; confirm for destructive |
| POST | `/api/v1/display/events/inject` | loopback + display token (dev/test) |

## Setup-public (while incomplete)

| Method | Path | Class |
|--------|------|-------|
| GET | `/setup`, `/first-boot`, `/servers` | setup-public pages |
| GET/PUT/POST | `/api/v1/first-boot/*` | setup-public (credentials/complete/factory-reset rate limited; reopen/factory need auth factors) |
| GET | `/api/v1/status/foundation`, `/setup`, `/hardware` | setup-public |
| GET | `/api/v1/hardware/diag`, `/api/v1/providers` | setup-public |
| * | `/api/v1/setup/*` | setup-public (Minecraft create wizard) |
| * | `/api/v1/network/*` | setup-public while incomplete; else auth |

## Authenticated (post-setup default)

| Method | Path | Class |
|--------|------|-------|
| GET | `/` | auth page (redirects to setup/first-boot if needed) |
| POST | `/auth/logout` | auth-write |
| POST | `/api/v1/auth/change-password` | auth-write + rate limit |
| GET | `/api/v1/minecraft` | auth-read |
| POST | `/api/v1/minecraft/start` | auth-write; blocked until setup complete |
| POST | `/api/v1/minecraft/stop\|restart\|recover` | privileged/destructive (`confirm=true`) |
| GET/PUT/POST | `/api/v1/minecraft/settings` | auth-write |
| GET | `/api/v1/console` | auth-read; blocked until complete |
| POST | `/api/v1/console/command` | auth-write + allowlist + rate limit |
| GET/POST/PUT/DELETE | `/api/v1/backups*` | auth; create/delete/restore privileged (`confirm` on delete/restore) |
| * | `/api/v1/files*` | auth-write; blocked until complete |
| * | `/api/v1/servers*` | auth; DELETE requires `confirm=true` |
| * | `/api/v1/players*` | auth-write |
| * | `/api/v1/mods*` | auth-write |
| * | `/api/v1/join*` | auth; blocked until complete |
| * | `/api/v1/update*` | auth; blocked until complete |
| GET | `/api/v1/system`, `/status`, `/system/thermal` | auth-read |
| POST | `/api/v1/system/shutdown\|reboot` | privileged (`confirm=true` + rate limit) |
| POST | `/api/v1/system/fan-test` | auth-write |
| GET | `/api/v1/status/*` (ops/thermal/crash/backups/minecraft/system) | auth-read (foundation/setup/hardware also setup-public) |
| GET/PUT | `/api/v1/appliance` | auth-write |
| GET/POST | `/api/v1/security/tls*` | auth-write |

## Factory reset / reopen

| Method | Path | Class |
|--------|------|-------|
| POST | `/api/v1/first-boot/reopen` | privileged (admin password + confirm) |
| POST | `/api/v1/first-boot/factory-reset` | privileged (admin password or recovery token + confirm) |

## Middleware summary

`AuthenticationMiddleware` (`app/core/security.py`):

1. Issue CSRF on safe methods when session exists
2. Allow public / setup-public paths
3. Block control prefixes while setup incomplete → **403**
4. Require configured admin + authenticated session
5. Require CSRF header on mutating authenticated/API requests (login/setup exempt)
