# Display UI Architecture — Prototype v1.0 (Checkpoint 5)

## Decision

**Chosen:** Chromium kiosk loading a dedicated lightweight MineBox UI at  
`http://127.0.0.1:8080/display` (800×480 fullscreen), talking to the existing FastAPI backend.

**Curses fallback:** `minebox-ui.service` / `python3 main.py` on tty1 remains available when `display.fallback = curses` or the graphical stack fails.

## Why Chromium kiosk

| Requirement | Chromium kiosk | Native Python GUI | Reuse full web dashboard |
|-------------|----------------|-------------------|---------------------------|
| Share backend API/state | Yes | Would duplicate or still need HTTP | Yes, but UI wrong size |
| 800×480 fullscreen, no chrome | Yes (`--kiosk`) | Possible | Heavy `index.html` unsuitable |
| Encoder as keyboard-like focus | Yes (events → focus model) | Yes | Not designed for it |
| Recover after backend restart | Yes (degraded page + reconnect) | Yes | Yes |
| systemd launch | Yes | Yes | Yes |
| Avoid full desktop if practical | Cage/openbox + Chromium | Needs toolkit stack | Same as kiosk |
| No touch / no mouse | Focus UI | Focus UI | Pointer-oriented today |
| Least new business logic | **Best** | Risk of second control path | Would need major rewrite |

## Rejected alternatives

1. **Evolve curses into the primary product UI** — kept as recovery; cannot meet finished appliance visual/kiosk expectations without becoming a parallel product.
2. **Qt / pygame / Tk native GUI** — new dependency surface, duplicates screens/actions already served by API, weaker reuse of CP4 auth/status endpoints.
3. **Point kiosk at existing `/` dashboard** — desktop density, scrolling, pointer assumptions; fails “readable from several feet” and focus navigation.

## Components

```
HAL (mock/Pi5) ──► display event bridge ──► /api/v1/display/events
                                              │
Chromium kiosk ──► /display (HTML/CSS/JS) ──► /api/v1/display/snapshot|action
                                              │
                                         FastAPI services (shared)
```

| Piece | Role |
|-------|------|
| `app/web/templates/display.html` + `static/display/*` | Appliance screens |
| `app/display/` | Event types, bridge, action map, local trust helpers |
| `app/api/routes/display.py` | Snapshot, events, scoped actions |
| `scripts/minebox_kiosk_launch.sh` | Chromium flags + profile + DPMS |
| `minebox-display.service` | Autostart graphical UI |
| `minebox-ui.service` | Curses recovery |

## Encoder GPIO

Encoder A/B/switch remain **NOT_CONFIGURED** until PCB verification. Navigation is validated via mock HAL and keyboard mappings. No pin numbers invented.
