# Hotspot — Prototype v1.0

## Behavior

- Starts at boot via `hostapd.service` + `dnsmasq.service`
- Subnet `192.168.4.0/24`, gateway `192.168.4.1`
- Channel **11**, dnsmasq **`no-resolv`** (no public DNS dependency for local SoftAP)
- Dashboard: `http://192.168.4.1` (port 80 captive helper → 8080)
- Minecraft: `192.168.4.1:25565`
- Survives uplink loss; NAT is separate (see Internet_Sharing.md)

## Recovery

- USB SoftAP adapter removal: role layer marks unresolved; does **not** silently steal the uplink radio without warning when a persisted identity is stale
- Reinsert: identity match restores assignment
- `POST /api/v1/network/recovery/retry` for manual retry (rate-limited burst)

## Secrets

Hotspot PSK is never returned by status APIs. Rotation is via first-boot / secret rotation (CP4).
