# First Boot — Prototype v1.0

Works over SoftAP (`http://192.168.4.1`) without internet.

## Flow

1. **Admin account** — `/auth/setup` (Argon2id password, ≥12 chars, not bootstrap defaults)
2. **Minecraft wizard** — `/setup` (provider, version, RAM, EULA, optional Wi‑Fi)
3. **Credential rotation** — `/first-boot`
   - Hotspot SSID/PSK (required; not `mineboxsetup`)
   - RCON password rotation (default on)
   - OS `minebox` password (preferred) or explicit defer
4. **Complete** — `POST /api/v1/first-boot/complete`

Setup is resumable via `/var/lib/minebox/first_boot_wizard.json` (passwords never stored there).

## Completion rules

Setup is complete only when:

- admin configured
- Minecraft setup marker/servers present
- required rotations done (hotspot + RCON; OS rotated or deferred)

Until then, control APIs (start/stop, console, restore, shutdown, files, updates) return **403**.

## Re-enter setup

`POST /api/v1/first-boot/reopen` with admin password + `confirm=true`.

## OS password limitation

Preferred: rotate the `minebox` Linux account via `/opt/minebox/scripts/minebox_set_os_password.py` (sudoers allowlist, password on stdin).

If the helper is unavailable or sudo fails, first-boot marks OS rotation as **deferred** (not claimed complete), attempts to disable password SSH, and documents local console recovery. See [Privileged_Operations.md](Privileged_Operations.md).

## Post-flash validation

```bash
PYTHONPATH=/opt/minebox python3 /opt/minebox/scripts/minebox_first_boot_check.py
```

Does not print secrets. See [Installation.md](Installation.md).
