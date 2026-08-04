# Remote Access — Prototype v1.0

Optional. **Disabled by default.** Local hotspot/LAN operation never depends on it.

## Provider interface

`networking.remote_access.RemoteAccessProvider` — first implementation is Tailscale.

## States

`NOT_INSTALLED` · `DISABLED` · `AUTH_REQUIRED` · `CONNECTING` · `CONNECTED` · `DEGRADED` · `ERROR`

## Security

- Administrator session + CSRF + rate limits
- Auth keys only in POST JSON body (never query strings)
- Strict subprocess argv to `tailscale` binary
- Keys never logged; redacted in support bundles
- Enabling Tailscale does **not** bypass dashboard login

## API

| Method | Path |
|--------|------|
| GET | `/api/v1/remote-access/status` |
| POST | `/api/v1/remote-access/enable` |
| POST | `/api/v1/remote-access/disable` (`confirm=true`) |
| POST | `/api/v1/remote-access/logout` (`confirm=true`) |
| POST | `/api/v1/remote-access/exposure` |

See [Tailscale.md](Tailscale.md) and [Remote_Minecraft.md](Remote_Minecraft.md).
