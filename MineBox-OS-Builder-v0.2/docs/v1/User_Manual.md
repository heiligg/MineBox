# MineBox User Manual — Prototype v1.0

Version `1.0.0-prototype.1`. Prototype appliance — not mass-production.

## Local front display (800×480)

When graphical mode is enabled, the front panel shows MineBox Home with large status text.

**Navigate:** turn the rotary encoder clockwise/counter-clockwise to move the gold focus box.  
**Select:** press the encoder knob.  
**Back:** short-press the left button.  
**Home:** hold the left button.  
**Context:** short-press the right button (opens System).  
**Power menu:** hold the right button.

If the encoder is unplugged, short left/right buttons temporarily move the focus again (fallback).

### Common tasks

- **Start/stop Minecraft** — Home → Server → Start / Stop (confirm Stop/Restart)  
- **Backup** — Home → Backups → Create backup (restore is done in the web dashboard)  
- **Network info** — Home → Network (hotspot password is never shown)  
- **Shut down** — Home → Power → Shut down → Confirm (or hold Right for Power)

### First boot

If the panel says **Setup required**, join Wi‑Fi **MineBox-Setup** and open **http://192.168.4.1** on a phone/laptop to finish setup. Server controls stay locked until setup completes.

Missing encoder at first boot only warns and falls back to two-button navigation — setup still works.

### If the panel cannot reach the backend

The display shows **Backend unavailable**. Wait for reconnect, or use the curses recovery UI on the local console (tty1).

### Web dashboard

On the same network: `http://<minebox-ip>:8080` (or SoftAP `http://192.168.4.1`). Full file/console/restore tools live there.

### Encoder note

Hardware Revision D uses the **Adafruit Seesaw rotary encoder (Product 5880)** over I²C as the primary control. See `Encoder.md` and `Hardware_Controls.md` for wiring and behavior.
