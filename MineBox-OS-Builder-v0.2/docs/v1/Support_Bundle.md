# Support Bundle — Network diagnostics (Checkpoint 6)

## API

`GET /api/v1/network/support-bundle` (authenticated after setup)

## Includes (redacted)

- Interface inventory + role assignment
- Hotspot / hostapd / dnsmasq hints
- nftables validation summary + excerpt
- Connectivity-check results
- Tailscale status without keys or unnecessary node secrets
- Recovery errors

## Excludes

- Hotspot PSK / Wi‑Fi passwords
- Tailscale auth keys
- Private keys / session secrets
- Raw unredacted logs containing secrets

Builder: `networking.support_bundle.build_network_support_bundle()`.
