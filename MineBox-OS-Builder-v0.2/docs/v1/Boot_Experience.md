# Boot Experience — Prototype v1.0 (Checkpoint 7)

## Image packaging

- Plymouth theme under `app/boot/minebox-plymouth-theme/`
- Installed during `install.sh` / pi-gen `00-run-chroot` when Plymouth is present
- Chromium kiosk + curses tty1 both enabled on complete images

## Boot sequence (summary)

See [Image_Build.md](Image_Build.md) for the full diagram. SoftAP and local UI come up without waiting for internet.

## Not claimed validated on physical hardware

Quiet-boot splash rendering and full SD flash boot on Raspberry Pi 5 are **prepared** in the image stages but **not** physically validated in the Checkpoint 7 development environment (requires Docker image build + Pi hardware).

## Recovery

- Curses UI: `minebox-ui.service` on `/dev/tty1`
- Backend health: `http://127.0.0.1:8080/api/v1/health`
- SoftAP dashboard: `http://192.168.4.1:8080`
- Display degraded screen shows reconnect + fallback hint when API is down
- See [Appliance_Recovery.md](Appliance_Recovery.md)
