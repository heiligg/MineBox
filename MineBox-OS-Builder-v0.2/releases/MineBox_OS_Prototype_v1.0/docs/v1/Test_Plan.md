# Test Plan — Prototype v1.0

## Automated (CI / desktop)

From `MineBox-OS-Builder-v0.2`:

```bash
export PYTHONPATH=app
export MINEBOX_FORCE_MOCK_HARDWARE=1
export MINEBOX_HARDWARE_PROFILE=mock
export MINEBOX_CONFIG="$PWD/config/minebox.example.toml"
export MINEBOX_HARDWARE_CONFIG="$PWD/config/hardware.example.toml"
export MINEBOX_RUNTIME_DIR="$PWD/.test-runtime"
python -m unittest discover -s tests -v
```

On Windows PowerShell:

```powershell
$env:PYTHONPATH = "app"
$env:MINEBOX_FORCE_MOCK_HARDWARE = "1"
$env:MINEBOX_HARDWARE_PROFILE = "mock"
$env:MINEBOX_CONFIG = "$PWD\config\minebox.example.toml"
$env:MINEBOX_HARDWARE_CONFIG = "$PWD\config\hardware.example.toml"
$env:MINEBOX_RUNTIME_DIR = "$PWD\.test-runtime"
python -m unittest discover -s tests -v
```

### Coverage by checkpoint

| CP | Areas |
|----|--------|
| 2 | Config, secrets, HAL mock, states |
| 3 | Providers, lifecycle, health, backups, thermal, shutdown, RCON allowlist, hotspot check-project |
| 4 | Argon2id auth, CSRF, rate limit, setup gating, factory reset preserve worlds, docs off by default, route inventory doc, no CORS middleware |
| 5 | Display nav state machine, event bridge inject/disconnect, loopback trust, kiosk script flags, service unit, curses fallback retained, no invented encoder GPIO |
| 6 | Interface roles (override/stale/missing), nftables generate/validate, sharing off without uplink, Tailscale default/disable confirm, support-bundle redaction, recovery burst limit |
| 7 | Idempotent installer flags, canonical sudoers, SoftAP render dry-run, unit ordering (no network-online on API/UI), validate_install scenarios, firstboot render hook, update_apply sudoers source |
| 8 | Version consistency, release exclusions, OpenAPI off, no forced mock hardware, docs links, nftables, first-boot check, archive verify |

### Display development mode

```powershell
$env:PYTHONPATH = "app"
$env:MINEBOX_FORCE_MOCK_HARDWARE = "1"
python app/scripts/minebox_display_dev.py
```

Open `http://127.0.0.1:8080/display/dev` (800×480 CSS). Keyboard: arrows/Enter/Esc; `[` `]` buttons; `{` `}` holds.

## Physical / appliance (manual)

| Area | Test |
|------|------|
| Buttons | Short/hold left/right on BCM23/17 |
| Encoder/LEDs/fan GPIO | Deferred — NOT_CONFIGURED |
| Display | Chromium kiosk 800×480; focus nav; degraded reconnect |
| Curses fallback | `minebox-ui` on tty1 still works |
| Encoder | Mock/dev until PCB pinout; do not invent pins |
| Hotspot | SoftAP without uplink; dashboard `http://192.168.4.1` |
| First boot | Admin → Minecraft setup → credential rotation → complete |
| Auth | Login fail/success; logout; password change |
| CSRF | Mutating call without token rejected |
| Ethernet / Wi‑Fi client | LAN dashboard + Minecraft join |
| Server lifecycle | Paper/Vanilla start/stop/restart with confirm |
| Backup/restore | Running + stopped; confirm restore/delete |
| Factory reset | Worlds preserved by default |
| Power | Shutdown/reboot confirm via API |
| OS password | Helper rotates `minebox`, or deferred + console path |
| Failed internet | Local SoftAP + Minecraft still work |

## Not claimed in Checkpoint 6

Physical dual-radio/HDMI validation on Pi, real encoder GPIO, installer/OTA packaging (CP7), signed release packaging (CP8).
