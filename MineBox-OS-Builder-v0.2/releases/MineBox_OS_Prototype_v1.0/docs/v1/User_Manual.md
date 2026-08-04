# MineBox User Manual — Prototype v1.0

Version `1.0.0-prototype.1`. Prototype appliance — not mass-production.

## Local front display (800×480)

When graphical mode is enabled, the front panel shows MineBox Home with large status text.

**Navigate:** turn the knob (or use short left/right buttons) to move the gold focus box.  
**Select:** press the knob (or hold the right button).  
**Back:** hold the knob (or hold the left button).

### Common tasks

- **Start/stop Minecraft** — Home → Server → Start / Stop (confirm Stop/Restart)  
- **Backup** — Home → Backups → Create backup (restore is done in the web dashboard)  
- **Network info** — Home → Network (hotspot password is never shown)  
- **Shut down** — Home → Power → Shut down → Confirm  

### First boot

If the panel says **Setup required**, join Wi‑Fi **MineBox-Setup** and open **http://192.168.4.1** on a phone/laptop to finish setup. Server controls stay locked until setup completes.

### If the panel cannot reach the backend

The display shows **Backend unavailable**. Wait for reconnect, or use the curses recovery UI on the local console (tty1).

### Web dashboard

On the same network: `http://<minebox-ip>:8080` (or SoftAP `http://192.168.4.1`). Full file/console/restore tools live there.

### Encoder note

Until hardware pinout is verified, encoder navigation is provided by mock/dev keyboard mappings on developer machines; physical encoder wiring is not invented in software.
