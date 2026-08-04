# MineBox OS Prototype v1.0

**Version:** `1.0.0-prototype.1`  
**Status:** Prototype — software package validated; not mass-production ready.

MineBox is a Raspberry Pi 5 appliance for hosting a local Minecraft server with SoftAP setup, a web dashboard, an optional 800×480 Chromium kiosk, and a curses recovery UI.

## Quick start

**Flash (when you have a built image):** write the `.img` / `.img.xz` to an SD card, boot the Pi 5, join SoftAP, complete first-boot.

**Build image (Linux + Docker):**

```bash
./check-project.sh
./build.sh --docker
```

See [docs/v1/Image_Build.md](docs/v1/Image_Build.md). Image generation was **not** performed in every developer environment — check `RELEASE_MANIFEST.json` for status.

**Manual install on Raspberry Pi OS:**

```bash
sudo bash app/install.sh
PYTHONPATH=/opt/minebox python3 /opt/minebox/scripts/minebox_first_boot_check.py
```

See [docs/v1/Installation.md](docs/v1/Installation.md).

## Documentation

| Doc | Topic |
|-----|--------|
| [Installation](docs/v1/Installation.md) | Install / uninstall |
| [First Boot](docs/v1/First_Boot.md) | Wizard |
| [User Manual](docs/v1/User_Manual.md) | Operators |
| [Administrator Guide](docs/v1/Administrator_Guide.md) | Day-2 ops |
| [Known Limitations](docs/v1/Known_Limitations.md) | Honest gaps |
| [Release Checklist](docs/v1/Release_Checklist.md) | Gates |
| [Final Release Audit](docs/v1/Final_Release_Audit.md) | Audit |
| [Hardware Test Plan](docs/v1/Prototype_Hardware_Test_Plan.md) | Physical matrix |

## Default bring-up credentials (rotate immediately)

- SoftAP SSID: `MineBox-Setup` (bootstrap PSK must be rotated in first-boot)
- OS user: `minebox` / `minebox` (image); change before distribution
- No shipped dashboard admin password — created during setup

## Tests

```bash
export PYTHONPATH=app MINEBOX_FORCE_MOCK_HARDWARE=1
python -m unittest discover -s tests -v
```

## License

No LICENSE file is bundled in this prototype tree unless added by the distributor.
