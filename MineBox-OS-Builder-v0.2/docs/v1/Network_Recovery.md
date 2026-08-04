# Network Recovery — Prototype v1.0

## Covered failures

- Hotspot/uplink adapter missing or reinserted
- Interface rename / stale role file
- hostapd / dnsmasq failure
- NetworkManager restart
- nftables validation failure
- DHCP/subnet conflict (reported; manual intervention)

## Loop protection

`networking.recovery`: max **5** attempts / **300s** window. Manual retry: `POST /api/v1/network/recovery/retry`.

## Principles

- Preserve SoftAP local access when possible
- Log concrete reasons
- Expose `recovery.progress` / `last_error` in network status
- Never silently reassign a random Wi‑Fi adapter to hotspot when identity is stale
