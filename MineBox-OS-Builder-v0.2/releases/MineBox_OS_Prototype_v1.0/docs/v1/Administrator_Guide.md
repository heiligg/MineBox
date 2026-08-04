# Administrator Guide — MineBox OS Prototype v1.0

## Day-2 operations

| Task | Command / path |
|------|----------------|
| API health | `curl -sS http://127.0.0.1:8080/api/v1/health` |
| First-boot check | `python3 /opt/minebox/scripts/minebox_first_boot_check.py` |
| Install validate | `python3 /opt/minebox/scripts/minebox_validate_install.py` |
| SoftAP re-render | `python3 /opt/minebox/scripts/minebox_render_hotspot_configs.py` |
| API logs | `journalctl -u minebox-api -f` |
| Minecraft logs | `journalctl -u minecraft -n 80` |
| Support bundle | Dashboard / network support-bundle API (redacted) |

## Users and privileges

- Dashboard/API: user `minebox` (not root)
- Privileged actions: `/etc/sudoers.d/minebox` allowlist — [Privileged_Operations.md](Privileged_Operations.md)
- OS console: `minebox` account; rotate password on first boot

## Networking

- SoftAP: hostapd + dnsmasq + nftables — [Hotspot.md](Hotspot.md), [Firewall.md](Firewall.md)
- Roles: [Interface_Roles.md](Interface_Roles.md)
- Tailscale optional: [Tailscale.md](Tailscale.md), [Remote_Access.md](Remote_Access.md)

## Minecraft

- Lifecycle via API preferred — [Minecraft_Lifecycle.md](Minecraft_Lifecycle.md)
- Backups: [Backup_Restore.md](Backup_Restore.md)
- Providers: Paper/Vanilla supported; Forge/Fabric experimental

## Updates

See [Updates.md](Updates.md). Prototype Git OTA is not a production updater.

## Recovery

[Appliance_Recovery.md](Appliance_Recovery.md), [Crash_Recovery.md](Crash_Recovery.md), [Network_Recovery.md](Network_Recovery.md)

## Security baseline

- OpenAPI off unless `MINEBOX_DEV_MODE` / `MINEBOX_ENABLE_DOCS`
- CSRF + sessions + rate limits on mutating routes
- No committed production admin password
