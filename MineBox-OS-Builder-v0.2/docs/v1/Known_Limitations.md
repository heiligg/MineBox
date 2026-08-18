# Known Limitations — Prototype v1.0

Updated at Checkpoint 8 completion (`1.0.0-prototype.1`).

**This release is a prototype, not mass-production firmware.**

## Hardware

- Button GPIOs are **GPIO17** (left / SW1) and **GPIO27** (right / SW2), active-low.
- Encoder is I²C1 address `0x36`; optional INT is **GPIO22**. LED / fan GPIO remain **NOT_CONFIGURED**.
- CM5 profile is a placeholder.
- Dual-radio hotspot **logical** behavior is implemented; **physical** validation requires Raspberry Pi hardware (not claimed in CP8 packaging).

## Networking

- Hotspot works **without internet**; internet sharing is optional.
- SoftAP templates may seed `wlan0` at image bake; first boot / render helper rewrites from interface roles.
- Tailscale is optional, **disabled by default**, and not required for local play.
- No public port-forward / UPnP automation.
- Captive helper answers local probes only — not full internet captive-portal emulation.

## Display UI

- Chromium kiosk `/display` + curses fallback.
- Quiet-boot Plymouth splash prepared; physical splash quality not validated here.
- Complex Tailscale setup remains web-only.

## Minecraft / backups / security

- Paper + Vanilla SUPPORTED; Forge/Fabric EXPERIMENTAL.
- Restore/delete/stop/restart require confirmations.
- OS password rotation may be deferred when helper/sudo unavailable.
- Image default OS password must be rotated before distribution.
- Bootstrap SoftAP PSK must be rotated during first-boot.

## Installer / image

- Full pi-gen Docker image build may be **pending** depending on host (see release manifest `image_status`).
- Chromium package name can differ (`chromium` vs `chromium-browser`).
- Minecraft JAR / EULA never baked into the image (license).

## Updater

- Git-based OTA remains the prototype mechanism (not a signed production updater).

## Validation honesty

| Layer | CP8 claim |
|-------|-----------|
| Automated software tests | Performed |
| Image structure / scripts | Statically validated |
| Generated `.img` artifact | Only if manifest says so — never faked |
| Physical Pi hardware matrix | Separate; see Prototype_Hardware_Test_Plan.md |
