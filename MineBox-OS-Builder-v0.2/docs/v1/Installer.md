# Installer — Prototype v1.0 (Checkpoint 7)

## Purpose

Idempotent appliance install/upgrade for MineBox on Raspberry Pi OS (or a flashed MineBox image). Safe to re-run. Preserves `/opt/minecraft` worlds/backups and `/var/lib/minebox`.

## Entry points

| Path | Use |
|------|-----|
| `app/install.sh` | Dev / upgrade on a running Pi |
| `pi-gen/stage-minebox/*` | Image bake (preferred for appliances) |
| `scripts/minebox_validate_install.py` | Post-install checks |
| `scripts/minebox_render_hotspot_configs.py` | SoftAP configs from interface roles |

## `install.sh` options

```bash
sudo bash /opt/minebox/install.sh
sudo bash app/install.sh --dry-run
sudo bash app/install.sh --skip-packages
sudo bash app/install.sh --no-display
sudo bash app/install.sh --uninstall   # disables units; keeps user data
```

## What it does

1. Validates root (unless `--dry-run`)
2. Installs packages only via apt when needed (Chromium, xinit, hostapd, dnsmasq, nftables, Java, Avahi, Plymouth, …)
3. Ensures `minebox` / `minecraft` users and shared group
4. rsyncs app tree → `/opt/minebox` (excludes caches)
5. Installs canonical `/etc/sudoers.d/minebox` from `services/sudoers/minebox`
6. Installs systemd units; disables legacy `minebox-network.service`
7. Renders hostapd/dnsmasq/nft/networkd from resolved SoftAP iface
8. Enables API, captive, UI, hostapd, dnsmasq, nftables, Minecraft
9. Enables `minebox-display` only when Chromium + xinit exist
10. Runs `minebox_validate_install.py`

## Prerequisites

- Debian/Raspberry Pi OS with `apt-get`
- Root for real install
- Network for package fetch (or `--skip-packages` on a complete image)

## Upgrade / data preservation

- Worlds and backups under `/opt/minecraft` are never wiped by install or `--uninstall`
- Auth and runtime state under `/var/lib/minebox` are preserved
- OTA path: `minebox_update_apply.py` also syncs sudoers + re-renders SoftAP configs

## Validation

```bash
PYTHONPATH=/opt/minebox python3 /opt/minebox/scripts/minebox_validate_install.py
PYTHONPATH=/opt/minebox python3 /opt/minebox/scripts/minebox_validate_install.py --json --strict
```

## Related docs

- [Image_Build.md](Image_Build.md)
- [Systemd_Services.md](Systemd_Services.md)
- [Appliance_Recovery.md](Appliance_Recovery.md)
