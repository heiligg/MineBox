# Networking — Prototype v1.0 (Checkpoint 6)

## Overview

MineBox uses a dual-radio SoftAP design:

| Role | Typical device | Service |
|------|----------------|---------|
| Hotspot | Onboard Wi‑Fi (identity-resolved; often `wlan0`) | `hostapd` + `dnsmasq` + address `192.168.4.1` |
| Wi‑Fi uplink | USB or remaining Wi‑Fi | NetworkManager client |
| Ethernet uplink | `eth0` / `en*` | NetworkManager / dhcpcd |

**Hotspot works without internet.** Local dashboard and Minecraft remain available on `192.168.4.0/24` when uplink is down.

## Central status

`GET /api/v1/network/status` → `networking.state.snapshot()` used by web, display, setup, and support bundle.

## Ports (SoftAP clients)

| Port | Service |
|------|---------|
| UDP 67 | DHCP |
| UDP/TCP 53 | DNS (`no-resolv`, local only) |
| TCP 80 | Captive helper / dashboard front-door |
| TCP 8080 | FastAPI dashboard |
| TCP 25565 | Minecraft |

RCON (`25575`) and SSH are **not** exposed on the WAN/default policy.

## Key paths

- hostapd: `/etc/hostapd/hostapd.conf` (channel **11**)
- dnsmasq: `/etc/dnsmasq.d/` MineBox conf (`no-resolv`)
- nftables: `/etc/nftables.conf` (from `services/hotspot/minebox-hotspot.nft` or generated policy)
- Captive: `minebox-captive.service` → `scripts/minebox_captive.py`

## Related docs

[Hotspot.md](Hotspot.md) · [Interface_Roles.md](Interface_Roles.md) · [Firewall.md](Firewall.md) · [Internet_Sharing.md](Internet_Sharing.md) · [Remote_Access.md](Remote_Access.md)
