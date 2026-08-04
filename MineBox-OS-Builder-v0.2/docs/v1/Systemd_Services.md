# Systemd Services — Prototype v1.0 (Checkpoint 7)

## Service list

| Unit | Role | WantedBy |
|------|------|----------|
| `minebox-firstboot.service` | Oneshot dirs/EULA/SoftAP render | multi-user |
| `minebox-api.service` | FastAPI backend / dashboard | multi-user |
| `minebox-captive.service` | SoftAP captive helper :80 | multi-user |
| `minebox-ui.service` | Curses recovery UI tty1 | multi-user |
| `minebox-display.service` | Chromium 800×480 kiosk vt7 | graphical |
| `minecraft.service` | Launcher → JVM | multi-user |
| `minebox-update.service` | OTA apply (triggered) | — |
| `minebox-maintenance.timer` | Maintenance | timers |
| `hostapd.service` | SoftAP | multi-user |
| `dnsmasq.service` | DHCP/DNS SoftAP | multi-user |
| `nftables.service` | Firewall/NAT | multi-user |
| `systemd-networkd.service` | SoftAP addressing | multi-user |
| `NetworkManager.service` | Uplink Wi‑Fi/Ethernet | multi-user |

Legacy **disabled**: `minebox-network.service` (NM SoftAP guard). Bare `minebox.service` is not the appliance primary path.

## Ordering (SoftAP-first)

```
minebox-firstboot
        │
systemd-networkd ──► hostapd ──► dnsmasq
        │                 │
        └──── minebox-api ┴──► minebox-captive
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
   minebox-ui  minebox-display  minecraft
```

- API/captive/UI/display **must not** require `network-online.target` (no internet wait).
- Minecraft **Wants** `network-online` but does not hard-require it.

## Minecraft unit

| Field | Value |
|-------|--------|
| User/Group | `minebox` |
| WorkingDirectory | `/opt/minecraft` |
| ExecStart | `/usr/bin/python3 -m services.launcher` |
| PYTHONPATH | `/opt/minebox` |
| Restart | `on-failure` / 5s |
| StartLimit | 5 / 300s |
| KillSignal | `SIGINT` |
| TimeoutStartSec | `900` |
| TimeoutStopSec | `45` |

Unit file sources (kept aligned):

- `app/services/minecraft.service`
- `systemd/minecraft.service`
- `pi-gen/.../files/minecraft.service`

## Lifecycle commands

```bash
sudo systemctl start minecraft.service
sudo systemctl stop minecraft.service
sudo systemctl restart minecraft.service
systemctl is-active minecraft.service
journalctl -u minecraft.service -n 80 --no-pager
```

Preferred control path: MineBox API / lifecycle manager.

## Logging / timeouts

- Journal persistent, capped (`/etc/systemd/journald.conf.d/minebox.conf`)
- Global `DefaultTimeoutStopSec=120s` (`system.conf.d/minebox.conf`)
- Per-unit `TimeoutStartSec` / `TimeoutStopSec` as above

See [Appliance_Recovery.md](Appliance_Recovery.md), [Display_Kiosk_Setup.md](Display_Kiosk_Setup.md).
