# Display UI Security — Prototype v1.0

## Trust model

Local display actions use a **loopback-only display token**, not the administrator password.

| Property | Behavior |
|----------|----------|
| Token file | `/var/lib/minebox/display_token` (mode `0600`) |
| Header | `X-MineBox-Display-Token` |
| Cookie | `minebox_display` (HttpOnly, SameSite=Strict) |
| Peer check | Client IP must be loopback (`127.0.0.1` / `::1`) |
| Scopes | `server_start`, `server_stop`, `server_restart`, `backup_create`, `services_restart`, `device_reboot`, `device_shutdown` |
| Remote reuse | **Denied** — non-loopback requests get 403 even with a stolen token |
| Admin password | Never embedded in kiosk profile, JS, or unit files |
| Console | Raw console commands are **not** exposed on the display API |

## Session bootstrap

1. API startup ensures the display token file exists.
2. Kiosk launcher (or `/display` JS) calls `POST /api/v1/display/session` on loopback.
3. Cookie is set for subsequent same-origin display API calls.

## CSRF

Display API routes under `/api/v1/display/` use the display token model instead of the admin CSRF session. The desktop dashboard CSRF rules remain unchanged.

## Setup gating

Until first-boot is complete, display control actions return **403**. The UI shows the Setup Required screen with SoftAP instructions.
