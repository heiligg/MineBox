# MineBox OS

MineBox OS turns a small Linux board (Raspberry Pi 5) into a plug-and-play Minecraft server appliance. This repo is a monorepo:

- `MineBox-OS-Builder-v0.2/` — canonical, actively developed product (FastAPI web dashboard + REST API, curses appliance UI, Minecraft server management) and the pi-gen OS image builder.
- `minebox/` — legacy standalone v1.3.1 snapshot; treat as historical unless you specifically need that release.

There is no database; state is file-based.

## Cursor Cloud specific instructions

The canonical dev target is the **MineBox dashboard/API** under `MineBox-OS-Builder-v0.2/`. Standard commands live in `MineBox-OS-Builder-v0.2/setup-dev.sh` and `run-dashboard.sh`; run the dashboard with `bash run-dashboard.sh --reload` (serves on `http://0.0.0.0:8080`). Some shell scripts don't have the executable bit set — invoke them via `bash <script>.sh`.

Non-obvious things worth knowing:

- Writable state dir: the dashboard writes runtime state to `/var/lib/minebox` (auth `auth.json`, updates, mods, TLS). This directory is created by the appliance installer, not by `run-dashboard.sh`, so in a dev VM it must already exist and be writable or startup fails at import with `PermissionError: /var/lib/minebox`. If missing, create it once: `sudo mkdir -p /var/lib/minebox && sudo chown -R "$(id -u):$(id -g)" /var/lib/minebox`. (`MINEBOX_AUTH_FILE` only overrides the auth path, not the other hardcoded `/var/lib/minebox` writers.)
- Dev vs prod paths: `run-dashboard.sh` exports `MINEBOX_DEV_MODE=1`, `PYTHONPATH=./app`, and `MINEBOX_MINECRAFT_ROOT=./runtime/minecraft`. Minecraft servers live under `runtime/minecraft/` in dev (vs `/opt/minecraft` on the appliance) and start/stop use a locally tracked Java process instead of `minecraft.service`. `runtime/` is disposable dev state; do not commit it (nor `.venv/`).
- First-run flow: with no admin configured, `/` redirects to `/auth/setup` (create admin), then `/login`. Admin passwords must be ≥12 chars, not a common default, and must not start with `minebox`.
- Creating a Minecraft server downloads a real `server.jar` (~60 MB) from Mojang/loader APIs, so it needs outbound internet. Java (21) is available for running servers.
- `check-project.sh` validates the pi-gen OS image builder, not the dashboard. It currently fails on a pre-existing config drift (`hostapd.conf` `channel=1` vs the `channel=6` the checker expects) — unrelated to dashboard dev. For a quick Python sanity check use `python3 -m compileall app`.
- Building the OS image (`build.sh`) needs Docker, tens of GB of disk, and ultimately Pi hardware to flash; it is not runnable end-to-end in a generic cloud VM. There is no `pytest`/automated test suite.
