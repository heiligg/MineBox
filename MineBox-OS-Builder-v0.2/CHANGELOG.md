# Changelog — MineBox OS Prototype

All notable changes for the Prototype v1.0 line. No earlier public release history is claimed.

## [1.0.0-prototype.1] — 2026-08-03 — MineBox OS Prototype v1.0

### Checkpoint 8 — Validation and release

- Centralized version (`VERSION` / `core.version`)
- Final release audit, security cleanup for packaging
- First-boot validation script (`minebox_first_boot_check.py`)
- Prototype hardware test plan
- Release documentation set and `releases/MineBox_OS_Prototype_v1.0/` archive
- Release-specific automated tests
- Fixed API mock-hardware force on appliance path
- SoftAP render preferred over hard-coded `wlan0` in OTA apply

### Checkpoint 7 — Installer and image integration

- Idempotent `install.sh` with dry-run / uninstall preserving data
- pi-gen packages for Chromium/X/Plymouth/Avahi/hostapd/dnsmasq/nftables
- Dynamic SoftAP config renderer
- Systemd SoftAP-first ordering and StartLimit recovery
- Install validation script

### Checkpoint 6 — Networking

- Interface role resolver
- nftables policy generation and internet sharing toggle
- Optional Tailscale provider (disabled by default)
- Support bundle redaction
- Network recovery limits

### Checkpoint 5 — Display

- Chromium 800×480 kiosk `/display`
- HAL event bridge; loopback display token
- Curses tty1 fallback retained

### Checkpoint 4 — Auth and first boot

- Argon2id admin auth, sessions, CSRF, rate limits
- First-boot wizard and setup gating
- Factory reset preserving worlds by default
- OpenAPI disabled by default

### Checkpoint 3 — Minecraft operations

- Provider abstraction (Paper/Vanilla supported)
- Lifecycle manager, health, crash recovery
- Backup/restore with confirmations
- Thermal monitoring; safe shutdown

### Checkpoint 2 — Foundation

- TOML configuration and secrets separation
- Hardware abstraction (mock / Pi5 / CM5 stub)
- State models

### Checkpoint 1 — Audit

- Repository audit and architecture documentation
- Implementation plan

---

Prototype status: **not mass-production ready**. Physical Raspberry Pi validation is a separate matrix.
