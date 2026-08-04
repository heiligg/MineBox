# MineBox Configuration — Prototype v1.0

**Checkpoint:** 2  

## Layout

| Kind | Appliance path | Repo example |
|------|----------------|--------------|
| Non-secret settings | `/etc/minebox/minebox.toml` | `config/minebox.example.toml` |
| Hardware profile | `/etc/minebox/hardware.toml` | `config/hardware.example.toml` |
| Secrets | `/etc/minebox/secrets.env` (0600) | `config/secrets.example.env` |
| Runtime / generated | `/var/lib/minebox/` | — |
| Logs | `/var/log/minebox/` | — |

Legacy JSON settings under `~/.config/minebox/settings.json` remain for older appliance preferences (`services/settings.py`) and will be migrated gradually.

## Environment overrides (development / tests)

| Variable | Purpose |
|----------|---------|
| `MINEBOX_CONFIG` | Path to `minebox.toml` |
| `MINEBOX_HARDWARE_CONFIG` | Path to `hardware.toml` |
| `MINEBOX_CONFIG_DIR` | Base directory (default `/etc/minebox`) |
| `MINEBOX_SECRETS_FILE` | Secrets env file |
| `MINEBOX_RUNTIME_DIR` | Runtime state (default `/var/lib/minebox`) |
| `MINEBOX_HARDWARE_PROFILE` | Force `mock` / `raspberry_pi5` / `cm5` |
| `MINEBOX_FORCE_MOCK_HARDWARE` | `1` to avoid real GPIO |

## Validation

`core.minebox_config.load_config()` validates types and ranges. The API process calls this on startup and logs a readable error if validation fails.

Loader search order falls back to the repo example TOML files when `/etc/minebox` is absent (dev/CI).

## Covered settings

Device name, API/dashboard bind+port, Minecraft data path, Java path, default RAM, supported/experimental providers, hotspot SSID/subnet/address, interface-selection roles, internet-sharing flag, display mode/resolution, hardware profile, GPIO + debounce/long-press/button actions, LED/fan placeholders, backup retention, update channel, logging level.

## Secrets

See [Security_Model.md](Security_Model.md). Never put passwords or PSKs in TOML.
