# Minecraft Providers — Prototype v1.0

## Support levels

| Level | Meaning |
|-------|---------|
| `SUPPORTED` | Official v1 acceptance target |
| `EXPERIMENTAL` | Preserved; use with caution until integration tests pass |
| `UNAVAILABLE` | Not usable |
| `BROKEN` | Known non-functional |

## v1 providers

| Provider | Status | Module |
|----------|--------|--------|
| Vanilla | **SUPPORTED** | `minecraft/providers/vanilla.py` |
| Paper | **SUPPORTED** | `minecraft/providers/paper.py` |
| Fabric | **EXPERIMENTAL** | `minecraft/providers/fabric.py` |
| Forge | **EXPERIMENTAL** | `minecraft/providers/forge.py` |
| NeoForge | **EXPERIMENTAL** | Mapped via Forge provider + existing launcher/download paths |

Existing download/install code in `services/downloads.py` and `services/launcher.py` is **preserved**. Providers add capability metadata, validation, and Java requirements for UI/API.

## API

`GET /api/v1/providers` and setup status include `support_level` / `v1_official`.
