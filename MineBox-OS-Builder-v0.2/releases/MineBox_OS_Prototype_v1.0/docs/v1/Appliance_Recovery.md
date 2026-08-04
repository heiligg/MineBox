# Appliance Recovery — Prototype v1.0 (Checkpoint 7)

Principles: restart with limits, keep SoftAP + recovery console available, never wipe worlds, never brick the appliance.

## Service restart policy

| Unit | Restart | StartLimit |
|------|---------|------------|
| `minebox-api` | on-failure / 3s | 8 / 120s |
| `minebox-captive` | on-failure / 2s | 8 / 120s |
| `minebox-display` | on-failure / 5s | 5 / 120s |
| `minebox-ui` | on-failure / 2s | 8 / 120s |
| `minecraft` | on-failure / 5s | 5 / 300s |
| `hostapd` | on-failure / 3s | (drop-in) |

No arbitrary `sleep` as the primary sync mechanism — use `After=` / `Wants=` / `Requires=`.

## Failure playbooks

### Backend down

```bash
journalctl -u minebox-api.service -n 80 --no-pager
sudo systemctl restart minebox-api.service
curl -sS http://127.0.0.1:8080/api/v1/health
```

Curses UI on tty1 and SoftAP remain usable when API is restarting.

### Display / Chromium / X unavailable

- Kiosk unit not enabled or failing → curses `minebox-ui` on tty1
- Web dashboard still on `http://192.168.4.1:8080` (or LAN IP)
- Re-run: `sudo bash /opt/minebox/install.sh` (enables display only if Chromium+xinit exist)

### Hotspot adapter missing

```bash
PYTHONPATH=/opt/minebox python3 /opt/minebox/scripts/minebox_render_hotspot_configs.py
journalctl -u hostapd -u dnsmasq -n 50 --no-pager
# Network recovery API / docs: Network_Recovery.md
```

### Corrupt config

```bash
PYTHONPATH=/opt/minebox python3 /opt/minebox/scripts/minebox_validate_install.py --json
# Restore from example if needed (does not delete worlds):
sudo cp /opt/minebox/config/minebox.example.toml /etc/minebox/minebox.toml
sudo systemctl restart minebox-api.service
```

### Minecraft missing / crash loop

- Missing JAR is expected until first-boot wizard
- systemd StartLimit + lifecycle crash policy stop infinite loops
- Worlds under `/opt/minecraft` are never removed by installer/update

### Power recovery

After unclean power loss: services restart via systemd; Minecraft launcher + crash recovery restore a safe stopped/running state; SoftAP comes up without uplink.

### Failed update

See OTA logs under `/var/log/minebox` and `minebox-update.service`. Previous tree may remain at `/opt/minebox.previous` when the updater swaps trees. Worlds untouched.

## Logging

```bash
journalctl -u minebox-api -u minebox-display -u minebox-ui -u minecraft -u hostapd -b
```

## Related

- [Crash_Recovery.md](Crash_Recovery.md) (Minecraft lifecycle)
- [Network_Recovery.md](Network_Recovery.md)
- [Installer.md](Installer.md)
