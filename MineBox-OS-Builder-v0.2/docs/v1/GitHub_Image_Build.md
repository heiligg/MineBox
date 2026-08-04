# GitHub Image Build — MineBox OS Prototype v1.0

Automated Raspberry Pi 5 image generation via GitHub Actions (pi-gen + Docker).

Canonical builder tree: `MineBox-OS-Builder-v0.2/`  
Workflows live at the repository root: `.github/workflows/`

## What gets built

- 64-bit Raspberry Pi OS (`arm64` pi-gen branch)
- Base release from `config/minebox-pi5.conf` (`RELEASE=trixie`)
- Custom stage `pi-gen/stage-minebox`
- Compressed deploy artifact: `*.img.xz` (and SHA-256)

## Workflows

| Workflow | File | Trigger | Result |
|----------|------|---------|--------|
| Build image | `.github/workflows/build-image.yml` | `workflow_dispatch`, push to `main` (image-related paths), reusable `workflow_call` | Artifacts (30 days) |
| Draft release | `.github/workflows/release.yml` | Tag `v*` (e.g. `v1.0.0-prototype.1`) | Build + **draft** GitHub Release |
| Nightly | `.github/workflows/nightly.yml` | Daily cron + manual | Same as build image |

## Manual workflow

1. GitHub → **Actions** → **Build MineBox OS Image**
2. **Run workflow** → branch `main`
3. Wait (often 1–3+ hours; needs a large runner disk)
4. Download artifacts from the run summary

## Automatic workflow

Pushes to `main` that touch builder/image paths run `build-image.yml` automatically.

## Tag releases (draft)

```bash
git tag v1.0.0-prototype.1
git push origin v1.0.0-prototype.1
```

`release.yml` builds the image, verifies `SHA256SUMS`, and opens a **draft** prerelease with:

- `MineBox_OS_Prototype_v1.0_RPi5.img.xz` (stable name)
- `SHA256SUMS`
- `build-manifest.json`
- `README_RELEASE.md` / `CHANGELOG.md` when present

Publish the draft manually in the GitHub UI when ready. Releases are **not** published automatically.

## Artifact names

| Artifact | Contents |
|----------|----------|
| `MineBox-OS-RPi5-image` | `.img.xz`, optional `.img`, `SHA256SUMS`, `build-manifest.json` |
| `MineBox-OS-RPi5-build-logs` | pi-gen / `build.sh` / Docker logs |
| `MineBox-OS-RPi5-validation` | `validation.log`, manifest, checksums |

Retention: **30 days**.

## Expected outputs

Under `MineBox-OS-Builder-v0.2/output/` on the runner (and in artifacts):

- `MineBox_OS_Prototype_v1.0_RPi5.img.xz`
- `SHA256SUMS`
- `build-manifest.json`
- logs under `ci-artifacts/`

## Build manifest fields

See `build-manifest.json`:

- `minebox_version` (from `VERSION`)
- `git_commit`
- `workflow_run_id`
- `github_actions_url`
- `timestamp`
- `base_raspberry_pi_os`
- `pi_target` (Raspberry Pi 5)
- `included_services`
- `sha256`
- `compressed_filename` / optional `image_filename`

## How to flash

```bash
# Verify
sha256sum -c SHA256SUMS

# Flash (Linux) — replace /dev/sdX carefully
xz -dc MineBox_OS_Prototype_v1.0_RPi5.img.xz | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync
sync
```

On Windows/macOS, use Raspberry Pi Imager or balenaEtcher with the decompressed `.img` if required.

After first boot: join SoftAP, open `http://192.168.4.1`, complete first-boot. See [First_Boot.md](First_Boot.md) and [Installation.md](Installation.md).

## Local equivalent

```bash
cd MineBox-OS-Builder-v0.2
./check-project.sh
./build.sh --docker
```

Requires Linux, Docker, binfmt/qemu for arm64, and tens of GB free disk.

## Failure behavior

- Logs and validation outputs upload even when the build fails (`if: always()`).
- Image artifacts upload **only on success** (no partial images).
- Validation fails the job if the image is missing, too small, checksum-invalid, or MineBox files/version/services are missing from the staged rootfs.

## Related

- [Image_Build.md](Image_Build.md)
- [Installer.md](Installer.md)
- [Known_Limitations.md](Known_Limitations.md)
