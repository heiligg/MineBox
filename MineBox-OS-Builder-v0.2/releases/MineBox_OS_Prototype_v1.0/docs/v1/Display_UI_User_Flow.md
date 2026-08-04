# Display UI User Flow — Prototype v1.0

Resolution: **800×480** landscape, fullscreen kiosk.

## Controls (v1 defaults)

| Input | Intent |
|-------|--------|
| Encoder CW / Right button short | Next focus |
| Encoder CCW / Left button short | Previous focus |
| Encoder press / Right button hold | Select |
| Encoder long-press / Left button hold | Back / cancel |
| Dev keyboard | ←/↑ prev · →/↓ next · Enter select · Esc back · `[`/`]` buttons · `{`/`}` holds |

Focus is always outlined in gold. Menus wrap at ends.

## Screens

1. **Home** — device name, Minecraft state, players, temp, RAM, storage, network/hotspot/IP, time; actions: Server, Backups, Network, System, Power, Diagnostics  
2. **Server** — state-aware Start/Stop/Restart/Backup/Details  
3. **Server details** — health summary, support, crash summary (no secrets)  
4. **Backups** — latest/count/size/busy; Create backup (restore remains web-only in v1)  
5. **Network** — hotspot SSID/IP/clients, ethernet, Wi‑Fi uplink, internet, sharing, remote-access state, remote Minecraft exposure (no PSK/keys)  
6. **System** — thermal/fan/load/RAM/disk/uptime/version/profile/unresolved features  
7. **Power** — restart services; reboot/shutdown with confirmation  
8. **Confirm** — shows selected destructive action  
9. **Setup required** — SoftAP + `http://192.168.4.1`  
10. **Degraded** — backend unavailable + retry; hints curses on tty1  
11. **Hardware diagnostics** — live buttons/encoder; does not run server/power actions  

Idle on non-home screens returns home after ~120s.
