# Web Dashboard — Prototype v1.0 (Checkpoint 4)

Existing FastAPI + Jinja/static stack. No frontend rewrite.

## Pages

| Page | Path | Notes |
|------|------|--------|
| Login | `/login` | Inline HTML from auth routes |
| Admin create | `/auth/setup` | First administrator only |
| First-boot credentials | `/first-boot` | Hotspot/RCON/OS rotation |
| Minecraft setup | `/setup` | Provider/version/RAM/EULA |
| Home / status | `/` | Server controls, console, system metrics |
| Servers | `/servers` | Multi-server list / delete |
| Backups | `/#backups` | List, create, restore, delete |
| Network | `/#network` | Roles/status via `/api/v1/network/status`; SoftAP/client controls |
| Remote access | Security/network panels | Tailscale enable/exposure (web-only; off by default) |
| Settings | `/#settings` | Minecraft settings foundation |
| Security | `/#security` | Password change |
| Error | HTTP 401/403/404 handlers | HTML for browsers; JSON for `/api/*` |

Graphical 800×480 local UI: `/display` (Chromium kiosk). Desktop dashboard remains at `/`. Curses UI retained as fallback.

## Client security

- Cookie session (`minebox_session`); no auth tokens in `localStorage`.
- `web/static/js/csrf.js` injects `X-CSRF-Token` on mutating `fetch`.
- Destructive UI actions use `window.confirm` and send `confirm: true` where the API requires it.

## Protected destructive actions

Stop, restart, recover, restore, backup delete, server delete, shutdown, reboot, factory reset, password change — authenticated + CSRF + server-side confirmation where applicable.
