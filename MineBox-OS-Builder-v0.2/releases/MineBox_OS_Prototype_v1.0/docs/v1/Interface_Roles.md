# Interface Roles — Prototype v1.0

Roles are resolved by `networking.roles`, not by hard-coded `wlan0`/`wlan1` alone.

## Signals

- Interface name (last resort)
- MAC address
- USB vendor/product IDs
- sysfs path / USB topology
- wireless capability
- Config role hints (`hotspot_interface_role`, `client_interface_role`)
- Manual overrides: `MINEBOX_HOTSPOT_IFACE`, `MINEBOX_WIFI_UPLINK_IFACE`, `MINEBOX_ETHERNET_IFACE`, `MINEBOX_HOTSPOT_MAC`, `MINEBOX_HOTSPOT_USB`
- Exclusions: `MINEBOX_NETWORK_EXCLUDE`

## Persistence

`/var/lib/minebox/network_roles.json` stores **identity keys** (MAC/USB), so renames can be detected. Stale assignments produce a warning and refuse silent reassignment.

## API

`GET /api/v1/network/roles`
