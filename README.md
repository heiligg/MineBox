# MineBox OS

MineBox OS is a dedicated operating system for running Minecraft servers on dedicated hardware.

Current development targets:

- Raspberry Pi 5
- Radxa CM5 (future carrier)

## Active codebase

**Canonical tree:** [`MineBox-OS-Builder-v0.2/`](MineBox-OS-Builder-v0.2/)

Prototype v1 documentation: [`MineBox-OS-Builder-v0.2/docs/v1/`](MineBox-OS-Builder-v0.2/docs/v1/)

## CI image builds

GitHub Actions builds a bootable Raspberry Pi 5 image (pi-gen / Docker):

- Workflow: **Build MineBox OS Image** (`.github/workflows/build-image.yml`)
- Docs: [`MineBox-OS-Builder-v0.2/docs/v1/GitHub_Image_Build.md`](MineBox-OS-Builder-v0.2/docs/v1/GitHub_Image_Build.md)
- Tag `v*` → draft release with `.img.xz` (`.github/workflows/release.yml`)

## Archive

Legacy root `minebox/` sources and obsolete documents live under [`archive/`](archive/). Do not use them for installs or new features.
