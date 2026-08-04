# Security Model — MineBox OS Prototype v1.0 (Checkpoint 4)

## Trust boundary

MineBox is a local appliance. The SoftAP and LAN dashboard are trusted for owner setup and control. Remote access is **not** enabled in Prototype v1.

## Authentication

- Single local administrator account (Argon2id password hash).
- Cookie sessions (`minebox_session`), HttpOnly, SameSite=Lax, Secure when HTTPS/`FORCE_SECURE_COOKIES`.
- Session id regenerated on login; logout deletes server-side session.
- Login/setup rate limited; temporary lockout (not permanent).

## CSRF

Authenticated mutating browser requests require `X-CSRF-Token` matching the session CSRF token. Login/setup forms are exempt and rate-limited instead.

## Setup gating

Until first-boot credential rotation completes, control-plane APIs return **403**. Public: health, network summary, first-boot APIs, emergency recovery text.

## Secrets

- Stored in `AUTH_FILE` / `secrets.env` / `hotspot.env` with mode `0600`.
- Never returned in API JSON; never logged in plaintext.
- RCON and SoftAP PSK must be rotated off bootstrap defaults before setup is complete.

## Process privilege

- FastAPI runs as `minebox` (non-root).
- Privileged ops use sudoers allowlists / helpers (`minebox_set_os_password.py`, systemctl, nmcli subset).

## CORS / OpenAPI

- No credentialed CORS wildcard.
- OpenAPI/Swagger disabled unless `MINEBOX_DEV_MODE=1` or `MINEBOX_ENABLE_DOCS=1`.

## Factory reset

Clears admin/session/setup state by default; preserves Minecraft worlds/backups unless `erase_user_data=true` with dual confirmation.
