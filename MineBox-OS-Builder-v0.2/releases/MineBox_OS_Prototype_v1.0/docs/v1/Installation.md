# Installation — MineBox OS Prototype v1.0

## Options

1. **Flash appliance image** (preferred) — build with [Image_Build.md](Image_Build.md), write `.img` to SD, boot Pi 5.
2. **Manual install** on Raspberry Pi OS (64-bit, Bookworm/Trixie) — use the release `installer/` or repo `app/install.sh`.

## Manual install

```bash
cd MineBox_OS_Prototype_v1.0   # or MineBox-OS-Builder-v0.2
sudo bash app/install.sh
# or from release tree:
sudo bash installer/install.sh
```

Options: `--dry-run`, `--skip-packages`, `--no-display`, `--uninstall` (preserves worlds).

Validate:

```bash
PYTHONPATH=/opt/minebox python3 /opt/minebox/scripts/minebox_validate_install.py
PYTHONPATH=/opt/minebox python3 /opt/minebox/scripts/minebox_first_boot_check.py
```

## After install / flash

1. Join SoftAP `MineBox-Setup` (bootstrap PSK only until first-boot rotation).
2. Open `http://192.168.4.1` and complete [First_Boot.md](First_Boot.md).
3. Change OS password `minebox` before any shared distribution.

## Uninstall / reset

```bash
sudo bash /opt/minebox/install.sh --uninstall
```

Preserves `/opt/minecraft` and `/var/lib/minebox` by default. Factory reset via dashboard is separate ([Factory_Reset.md](Factory_Reset.md)).

## Related

- [Installer.md](Installer.md) (installer internals)
- [Appliance_Recovery.md](Appliance_Recovery.md)
- [Known_Limitations.md](Known_Limitations.md)
