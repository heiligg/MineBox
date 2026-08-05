# Hardware Controls — Revision D

Primary navigation is the **Adafruit Seesaw rotary encoder**. The existing left/right buttons remain installed as **secondary** controls.

---

## Control scheme

| Input | Intent | UI effect |
|-------|--------|-----------|
| Rotate CW | `next` | Move selection down |
| Rotate CCW | `prev` | Move selection up |
| Encoder press | `select` | Activate focused item |
| Encoder long-press | `back` | Secondary back (optional) |
| Left short | `back` | Back |
| Left hold | `home` | Home |
| Right short | `context` | Context (opens System screen — no UI redesign) |
| Right hold | `power` | Power menu |

---

## Fallback (encoder missing)

| Input | Intent |
|-------|--------|
| Left short | `prev` |
| Left hold | `back` |
| Right short | `next` |
| Right hold | `select` |

Chosen automatically via `resolve_action_map(encoder_available=…)`.

---

## Software map

| Layer | Path |
|-------|------|
| ActionMap | `app/display/actions.py` |
| Events | `app/display/events.py` |
| Bridge | `app/display/bridge.py` |
| Kiosk intents | `app/web/static/display/display.js` |
| Nav state machine | `app/display/nav.py` |
| Curses buttons | `app/gpio_buttons.py` |

---

## Timing defaults

| Control | Debounce | Long-press |
|---------|----------|------------|
| Buttons | 40 ms | 450 ms |
| Encoder switch | 15 ms | 700 ms |

Configured in `hardware.toml` (`[buttons]` / `[encoder]`).

---

## Related docs

- `Encoder.md` — Seesaw driver and wiring  
- `Hardware_Pinout.md` — pin table  
- `User_Manual.md` — end-user controls  
