# Troubleshooting — MineBox OS Prototype v1.0

## Quick checks

```bash
python3 /opt/minebox/scripts/minebox_first_boot_check.py
python3 /opt/minebox/scripts/minebox_validate_install.py
systemctl is-active minebox-api hostapd dnsmasq minebox-ui
curl -sS http://127.0.0.1:8080/api/v1/health
```

## SoftAP down

```bash
PYTHONPATH=/opt/minebox python3 /opt/minebox/scripts/minebox_render_hotspot_configs.py
sudo systemctl restart hostapd dnsmasq nftables
journalctl -u hostapd -u dnsmasq -n 50
```

See [Network_Recovery.md](Network_Recovery.md).

## Dashboard unreachable

- Confirm SoftAP IP `192.168.4.1` vs LAN IP
- `journalctl -u minebox-api -n 80`
- Captive helper: `minebox-captive.service` (port 80)

## Kiosk blank / Chromium missing

- Curses on tty1: `minebox-ui.service`
- Reinstall packages; `sudo bash /opt/minebox/install.sh` (enables display only if Chromium+xinit present)

## Minecraft won’t start

- JAR/EULA missing until wizard — expected
- `journalctl -u minecraft -n 80`
- StartLimit may cool down after crash loops — [Crash_Recovery.md](Crash_Recovery.md)

## Auth / first-boot stuck

- [First_Boot.md](First_Boot.md); bootstrap PSK must be changed
- OS password helper may defer if sudoers missing — reinstall sudoers from package

## Wrong Wi-Fi interface

```bash
PYTHONPATH=/opt/minebox python3 -c "from networking.roles import resolve_roles; print(resolve_roles())"
python3 /opt/minebox/scripts/minebox_render_hotspot_configs.py
```

## More

[Appliance_Recovery.md](Appliance_Recovery.md) · [Known_Limitations.md](Known_Limitations.md)
