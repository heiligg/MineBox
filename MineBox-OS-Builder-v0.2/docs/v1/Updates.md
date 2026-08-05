# Updates — MineBox OS Prototype v1.0

## Prototype mechanism

OTA uses Git checkout + `minebox-update.service` → `scripts/minebox_update_apply.py`.

This is a **prototype** path: integrity is best-effort; always keep backups of worlds.

## Private repository access

`heiligg/MineBox` is **private**. The Pi must authenticate or the dashboard shows **Latest commit unavailable**.

1. On the Pi, create a deploy key (if missing):

```bash
sudo -u minebox mkdir -p /home/minebox/.ssh
sudo -u minebox ssh-keygen -t ed25519 -f /home/minebox/.ssh/minebox_update -N ""
sudo -u minebox cat /home/minebox/.ssh/minebox_update.pub
```

2. GitHub → repo **Settings → Deploy keys → Add deploy key** (read-only). Paste the `.pub` key.

3. Point updates at SSH in `/etc/minebox/updates.conf`:

```bash
repo=git@github.com:heiligg/MineBox.git
branch=main
app_subdir=MineBox-OS-Builder-v0.2/app
```

4. Test:

```bash
sudo -u minebox GIT_SSH_COMMAND='ssh -i /home/minebox/.ssh/minebox_update -o IdentitiesOnly=yes' \
  git ls-remote git@github.com:heiligg/MineBox.git refs/heads/main
```

You should see a commit hash for `refs/heads/main`. Then use **Check for updates** in the dashboard.

If an HTTPS `repo=` URL is configured but the deploy key file exists, the updater rewrites it to SSH automatically.

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
- Private repos require a deploy key (above)
- Not suitable as sole recovery for corrupt OS images — re-flash SD instead
