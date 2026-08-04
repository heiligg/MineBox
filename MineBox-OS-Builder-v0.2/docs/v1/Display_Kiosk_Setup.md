# Display Kiosk Setup — Prototype v1.0

## Units

| Unit | Role |
|------|------|
| `minebox-api.service` | FastAPI backend |
| `minebox-display.service` | Chromium kiosk via `xinit` + `minebox_display_session.sh` |
| `minebox-ui.service` | Curses fallback on tty1 |

Enable graphical mode when Chromium/X are present:

```bash
systemctl enable minebox-api.service
systemctl enable minebox-display.service
# Keep minebox-ui enabled for recovery, or disable if only one VT should own the panel.
```

## Scripts

- `/opt/minebox/scripts/minebox_kiosk_launch.sh` — Chromium `--kiosk` flags, 800×480, dedicated profile, no first-run/password/crash bubbles  
- `/opt/minebox/scripts/minebox_display_session.sh` — minimal openbox (if present) + kiosk  

## DPMS / blanking

Launcher runs `xset s off`, `xset -dpms`, `xset s noblank` when `xset` exists. Documented best-effort; panel firmware may still blank.

## Packages (image)

Chromium (`chromium` / `chromium-browser`), `xinit`, optional `openbox`, `xset` (x11-xserver-utils).

## Crash recovery

`Restart=on-failure` with `StartLimitBurst=5` / `StartLimitIntervalSec=120` to avoid aggressive restart loops. Backend wait uses health polling (≤60s), not a single long sleep.

## Fallback

If the kiosk fails: use tty1 curses (`minebox-ui.service`) or SSH/local console. Graphical UI does **not** remove curses.
