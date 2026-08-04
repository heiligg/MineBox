# Privileged Operations — Prototype v1.0

## Principle

The FastAPI process runs as user `minebox` (non-root). Privileged work uses:

- `/etc/sudoers.d/minebox` exact-command allowlist
- narrowly scoped Python helpers under `/opt/minebox/scripts/`
- polkit rules for NetworkManager where installed

No arbitrary shell fragments from the web API.

## Sudoers allowlist (install / pi-gen / OTA apply)

Includes (among others):

- `systemctl` start/stop/restart for `minecraft`, `hostapd`, `dnsmasq`, `avahi-daemon`, `minebox-api`, `minebox-update`
- `systemctl reload` for `ssh` / `nftables` where listed
- `nft -f /etc/nftables.conf`
- `systemctl poweroff` / `systemctl reboot`
- helpers: `minebox_fix_minecraft_perms.py`, `minebox_install_avahi.py`, `minebox_ensure_java.py`, `minebox_ensure_tls.py`, `minebox_fan_test.py`, `minebox_render_hotspot_configs.py`
- **OS password:** `/usr/bin/python3 /opt/minebox/scripts/minebox_set_os_password.py minebox`  
  Password is supplied on stdin only; username argument must be `minebox`.

Canonical source: `app/services/sudoers/minebox` (installed by `install.sh`, pi-gen chroot, and OTA apply).

## Audited actions

| Action | Mechanism |
|--------|-----------|
| Shutdown / reboot | `sudo -n systemctl poweroff|reboot` via safe_shutdown after Minecraft stop |
| Hotspot PSK | Write secrets + hostapd.conf, then `systemctl restart hostapd` |
| Service restarts | Exact unit names only |
| OS password | `minebox_set_os_password.py` → `chpasswd` for `minebox` only |
| Factory reset | App-level file clears; no root shell |
| Tailscale | Fixed argv to `tailscale` binary only (`up`/`down`/`logout`/`status`); auth key via stdin-equivalent argv flag, never logged |
| nftables apply | Write generated policy + `nftables.service` (not arbitrary nft fragments from the web) |

## Failure modes

If sudo/helper is missing (dev/CI), OS password rotation is **deferred** (honest status), and password SSH disable is best-effort. Setup still completes with hotspot+RCON rotated.
