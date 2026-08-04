# Archive

This directory holds **legacy** MineBox code and **stale** documentation that must not be used for new development or appliance installs.

## Active implementation

Use:

- `MineBox-OS-Builder-v0.2/` — canonical appliance sources, pi-gen image stages, and OTA app tree (`app/` → `/opt/minebox`)

## Contents

| Path | Why archived |
|------|----------------|
| `legacy/minebox/` | Pre-dashboard / early curses-only tree from the repo root. Superseded by `MineBox-OS-Builder-v0.2/app`. |
| `stale-docs/INTERNET-SHARING.md` | Described NetworkManager shared mode; production SoftAP is hostapd + dnsmasq + nftables. |
| `stale-docs/UPDATER-V2.md` | Superseded by `app/scripts/minebox_update_apply.py` and related update services. |

## Still referenced?

- **No** active build scripts or runtime imports should reference `archive/legacy/minebox/`.
- Git history is preserved via `git mv` (files were not deleted).

If you need something from the archive, copy it into the Builder tree deliberately and update docs — do not point users at archived paths.
