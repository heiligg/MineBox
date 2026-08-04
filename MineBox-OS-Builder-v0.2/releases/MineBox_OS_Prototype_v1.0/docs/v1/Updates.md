# Updates — MineBox OS Prototype v1.0

## Prototype mechanism

OTA uses Git checkout + `minebox-update.service` → `scripts/minebox_update_apply.py`.

This is a **prototype** path: integrity is best-effort; always keep backups of worlds.

## Apply (on device)

Configured via `/etc/minebox/updates.conf` (repo/branch/subdir). Trigger from dashboard Updates or:

```bash
sudo systemctl start minebox-update.service
journalctl -u minebox-update -n 100 --no-pager
```

Apply preserves `/opt/minecraft` and durable auth under `/var/lib/minebox`, syncs sudoers from `services/sudoers/minebox`, and re-renders SoftAP configs.

## Manual upgrade

```bash
sudo bash /opt/minebox/install.sh
```

Idempotent; preserves user data.

## Rollback

If apply swaps trees, previous may remain at `/opt/minebox.previous` (when used). Restore by swapping directories and restarting `minebox-api`. Worlds are not stored under `/opt/minebox`.

## Limits

- Not signed binary releases
- Network required for Git fetch
- Not suitable as sole recovery for corrupt OS images — re-flash SD instead
