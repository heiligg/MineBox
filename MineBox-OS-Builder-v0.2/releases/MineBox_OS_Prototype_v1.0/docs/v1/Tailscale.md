# Tailscale — Prototype v1.0

## Defaults

- Not required for local use
- Disabled until owner enables via dashboard
- `expose_dashboard=false`, `expose_minecraft=false` until explicitly set

## Enable (web-only)

1. Install Tailscale on the appliance image (`tailscale` binary on PATH)
2. Sign in as MineBox admin
3. `POST /api/v1/remote-access/enable` with one-time `auth_key`
4. Optionally set exposure flags

## Cookies / HTTPS

Dashboard auth cookies remain `SameSite=Lax`; use HTTPS (`MINEBOX_SESSION_HTTPS_ONLY` / TLS helper) when accessing over Tailscale hostnames. CSRF remains required for mutations.

## Setup-incomplete

First-boot setup endpoints must not be treated as remotely trusted; complete setup on SoftAP/LAN before relying on Tailscale.
