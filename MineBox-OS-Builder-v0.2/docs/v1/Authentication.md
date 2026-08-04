# Authentication — Prototype v1.0

## Model

One local administrator account (`admin` by default username choice).

| Item | Behavior |
|------|----------|
| Password hash | **Argon2id** (`argon2-cffi`); legacy scrypt verified and upgraded on login |
| Session cookie | `minebox_session`, HttpOnly (Starlette), `SameSite=Lax` |
| Secure flag | Enabled when TLS is on or `MINEBOX_SESSION_HTTPS_ONLY=1` |
| Lifetime | `MINEBOX_SESSION_MAX_AGE` (default 14 days) |
| Fixation | Session cleared and CSRF rotated on login/setup |
| Logout | `POST /auth/logout` clears session |

## Endpoints

| Method | Path | Notes |
|--------|------|-------|
| GET | `/login` | Login page |
| POST | `/auth/login` | Rate limited; no CSRF required |
| GET/POST | `/auth/setup` | First admin create; rate limited |
| GET | `/api/v1/auth/status` | Configured/authenticated + first-boot summary |
| GET | `/api/v1/auth/csrf` | Issue/read CSRF token |
| POST | `/api/v1/auth/change-password` | Requires auth + CSRF; rate limited |

Failed logins are logged **without** passwords or hashes.
