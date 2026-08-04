# Internet Sharing — Prototype v1.0

## Config

`[network] internet_sharing = true|false` in `minebox.toml` (example default `true` for home NAT convenience).

## Runtime rules

Sharing is **active** only when:

1. Config enables it, and
2. A valid uplink interface is present

When uplink disappears, generated policy **omits** masquerade/forward sharing rules. SoftAP stays up as local-only.

## NAT

```
ip saddr 192.168.4.0/24 oifname != "<hotspot>" masquerade
```

Forward allows hotspot clients → uplink; does not open dashboard/SSH from the uplink into new inbound management sessions beyond established traffic.

## Status

`network.internet_sharing.active` / `.configured` / `.state` in `/api/v1/network/status`.
