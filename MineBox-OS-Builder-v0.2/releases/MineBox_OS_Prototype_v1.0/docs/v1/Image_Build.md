# Image Build — Prototype v1.0 (Checkpoint 7)

## Goal

Produce a flashable Raspberry Pi 5 SD image that boots into MineBox without manual package installation.

## Host requirements

- Linux host (or CI) with Docker (recommended: `./build.sh --docker`)
- Tens of GB free disk, internet for pi-gen package fetch
- `git`, `rsync`, `python3`, `bash`

Windows cannot run the full image build locally; use Linux/CI. Static validation: `./check-project.sh`.

## Build commands

From `MineBox-OS-Builder-v0.2`:

```bash
./check-project.sh
./build.sh --docker
# or: ./build.sh --native
```

Artifacts land in `output/`.

## Stage layout (`pi-gen/stage-minebox`)

| Stage | Role |
|-------|------|
| `00-install-minebox` | Packages + `/opt/minebox` tree + sudoers + API/captive/display units |
| `01-system-config` | tty1 UI, firstboot, minecraft unit, journald/timeouts |
| `02-dedicated-hotspot` | hostapd/dnsmasq/nft seed + enable SoftAP stack |
| `02-firstboot` | Console issue banner (pi-gen naming; separate from `minebox-firstboot`) |

`build.sh` rsyncs live `app/` into the stage before pi-gen runs.

## Packages baked into the image

From `00-packages` (plus hotspot stage): Python stack, `default-jre-headless`, NetworkManager, hostapd, dnsmasq, nftables, Avahi, Chromium, X (`xinit`/`xserver-xorg`/`openbox`), Plymouth, iw/rfkill, OpenSSH.

No Minecraft `server.jar` is included (license).

## Boot flow (appliance)

1. Firmware / kernel / Plymouth (theme installed when available)
2. `systemd` → `multi-user.target` (+ `graphical.target` for kiosk)
3. `minebox-firstboot.service` (oneshot; dirs, EULA stub, SoftAP render)
4. `systemd-networkd` + `hostapd` + `dnsmasq` + `nftables` (SoftAP `192.168.4.1`)
5. `minebox-api.service` → dashboard `:8080`
6. `minebox-captive.service` (port 80 helper)
7. `minebox-ui.service` on tty1 (curses recovery)
8. `minebox-display.service` on vt7 when Chromium/X present (kiosk `/display`)
9. `minecraft.service` via launcher (fails fast / StartLimit until JAR + EULA)

## Shutdown flow

1. API/lifecycle stop Minecraft (SIGINT / graceful)
2. systemd `TimeoutStopSec` on units (global default 120s via drop-in)
3. hostapd/dnsmasq stop; nftables flush per unit
4. journal preserved (`SystemMaxUse=200M`)

## SoftAP interface names

Image seeds configs for `wlan0`. On first boot, `minebox_render_hotspot_configs.py` rewrites hostapd/dnsmasq/networkd/NM-unmanaged/sysctl/nft from **resolved interface roles** — nothing permanently assumes a single adapter name after first boot.

## SSH / default credentials

`config/minebox-pi5.conf` sets `ENABLE_SSH=1` and first user `minebox` / `minebox`. Change before distributing images. Prefer completing the web first-boot wizard over leaving defaults.

## Image artifact status

Checkpoint 8 packaging **does not invent** a `.img` file. If this environment cannot run Docker/pi-gen, the release manifest records:

`image_status: not_generated_in_this_environment`

Exact build commands remain:

```bash
./check-project.sh
./build.sh --docker
```

Artifacts appear under `output/` when the build succeeds.

## Related

- [Installer.md](Installer.md)
- [Systemd_Services.md](Systemd_Services.md)
- [Boot_Experience.md](Boot_Experience.md)
- [Hotspot.md](Hotspot.md)
