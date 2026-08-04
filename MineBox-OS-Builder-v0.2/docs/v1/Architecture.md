# MineBox Architecture — Prototype v1.0 (Target)

**Status:** Living design — Checkpoints 1–3 implemented in-tree  
**Date:** 2026-08-01  
**Basis:** Existing MineBox-OS-Builder-v0.2 stack (preserve and evolve; do not greenfield rewrite)

### Checkpoint 2–3 additions (implemented)

| Area | Location |
|------|----------|
| Validated TOML config | `core/minebox_config.py`, `config/*.example.toml` |
| Secrets separation | `core/secrets_store.py`, `config/secrets.example.env` |
| Bootstrap incomplete state | `core/bootstrap.py` |
| Minecraft / health state models | `core/states.py`, `docs/v1/State_Models.md` |
| Shared status service | `core/state_service.py`, `api/routes/foundation.py` |
| HAL (mock / Pi5 / CM5) | `hardware/` |
| Providers | `minecraft/providers/` |
| Lifecycle + health | `services/lifecycle.py`, `services/minecraft_health.py` |
| Ops coordinator | `services/operations.py` |
| Backup/restore hardening | `services/backups.py` |
| Thermal / shutdown / crash | `services/thermal.py`, `safe_shutdown.py`, `crash_recovery.py` |
| Remote-access interface stub | `networking/remote_access.py` (disabled) |
| Legacy archive | `/archive` at repo root |

---

## 1. Goals

MineBox behaves as a **consumer appliance**:

1. Power on → splash → services → fullscreen UI (no desktop/terminal in normal use).
2. Encoder + two illuminated buttons drive the local UI; touchscreen not required.
3. Web dashboard on Ethernet, home Wi‑Fi, and MineBox SoftAP.
4. Minecraft lifecycle, backups, updates without requiring a shell.
5. Local operation without internet; optional remote access never weakens local defaults.
6. Future board (Radxa CM5) via **hardware abstraction**, not Pi-specific code scattered everywhere.

---

## 2. Process diagram (target)

```
                         ┌─────────────────────────────────────┐
                         │           systemd                   │
                         │  minebox-backend · minebox-display  │
                         │  minebox-minecraft · minebox-network│
                         │  (optional) minebox-hardware        │
                         └──────────────┬──────────────────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
          ▼                             ▼                             ▼
 ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
 │ minebox-display │◄─HTTP──►│ minebox-backend │◄───────►│ minebox-minecraft│
 │ (kiosk / 800x480│  API    │ FastAPI :8080   │  mgr    │ (java / systemd) │
 │  encoder UI)    │         │ state + auth    │         └─────────────────┘
 └────────┬────────┘         └────────┬────────┘
          │                           │
          │ HAL                       ├──────────► networking (NM / SoftAP)
          ▼                           ├──────────► backup / updates
 ┌─────────────────┐                  ├──────────► thermal / fan
 │ hardware HAL    │                  └──────────► logging / diagnostics
 │ Pi5 | mock | CM5│
 └─────────────────┘

 Web clients (LAN / SoftAP) ──HTTPS/HTTP──► minebox-backend
 Captive helper (port 80) ──redirect──► dashboard (optional thin process)
```

### Mapping from today’s processes

| Today | Target |
|-------|--------|
| `minebox-api.service` → `uvicorn app.main:app` | `minebox-backend.service` (same app evolved, or rename unit) |
| `minebox-ui.service` → `main.py` curses | `minebox-display.service` (curses or new 800×480 UI talking to API) |
| `minecraft.service` → Java | keep; backend owns lifecycle via `MinecraftManager` |
| `minebox-hotspot.service` + hostapd/dnsmasq/nft | `minebox-network` role (may stay multiple units) |
| `minebox-captive.service` | keep or fold into backend with privilege drop |
| in-process `gpio_buttons` in UI | HAL used by display (+ optional hardware service) |

---

## 3. Service boundaries

| Service | Owns | Must not own |
|---------|------|----------------|
| **Backend** | Auth, API, Minecraft control, backups, updates orchestration, system power (via polkit/sudoers), health, config validation, first-boot state | Raw GPIO bit-banging (prefer HAL); Minecraft JVM process (systemd/java child) |
| **Display** | Screens, encoder/button navigation, kiosk presentation, calling backend API | Privileged network changes; Minecraft file writes; secrets storage |
| **Minecraft unit** | JVM lifecycle under systemd | Dashboard HTTP; GPIO |
| **Network stack** | SoftAP, client Wi‑Fi, firewall, DHCP DNS policy | Minecraft world files |
| **Hardware HAL** | Buttons, encoder, LEDs, fan, temp sensors, reboot/shutdown request hooks | Business logic / auth |

---

## 4. API boundaries

**Primary interface:** HTTP JSON API on `127.0.0.1` and LAN/SoftAP bind addresses (today `:8080`).

**Consumers:**

1. Web dashboard (browser) — full API with session auth.
2. Display UI — same API with local session or loopback token (to be defined in Checkpoint 2; prefer one auth model).
3. Captive portal — minimal redirect / captive detection only.

**Documented surface (evolve from OpenAPI already exposed):**

- `/api/v1/status`, `/api/v1/players`, `/api/v1/metrics`
- `/api/v1/server/*`, `/api/v1/console`
- `/api/v1/backups/*`, `/api/v1/files/*`
- `/api/v1/network/*`, `/api/v1/wifi/*`, `/api/v1/hotspot/*`
- `/api/v1/system/*`, `/api/v1/updates/*`
- `/api/v1/auth/*`, `/api/v1/setup/*`
- **New:** `/api/v1/hardware/diag` (live inputs, no destructive actions)
- **New:** `/api/v1/health` structured health for updater rollback

**Privilege rule:** Unauthenticated callers get only setup (first-boot) and health/captive helpers. All control planes require admin session after setup.

---

## 5. Privilege boundaries

```
┌──────────────────────────────────────────────────────────┐
│ root (minimal)                                           │
│  - systemd                                              │
│  - hostapd / dnsmasq / nftables                         │
│  - optional: thin privileged helpers via polkit         │
└──────────────────────────────────────────────────────────┘
          ▲ sudoers / polkit (narrow commands)
┌──────────────────────────────────────────────────────────┐
│ minebox (service user)                                   │
│  - backend (uvicorn)                                    │
│  - display UI                                           │
│  - MinecraftManager file ops under /opt/minecraft       │
│  - HAL via gpiod (group gpio)                           │
└──────────────────────────────────────────────────────────┘
```

**Rules (non-negotiable for v1):**

- Do not run the web application as root (migrate captive portal off root or drop privileges after bind).
- No shell string concatenation for RCON/system commands.
- Secrets only under `/etc/minebox/` or `/var/lib/minebox/` with `0600`, never in git.
- Display and web both go through backend for destructive actions (shutdown, restore, network wipe).

---

## 6. Data storage locations

| Data | Path (current / target) | Notes |
|------|-------------------------|--------|
| Application code | `/opt/minebox` | OTA from GitHub `app_subdir` |
| Minecraft worlds / jars | `/opt/minecraft` | Preserve across OS image updates |
| Device config | `/etc/minebox/device.conf` | Existing |
| Auth secrets | `/etc/minebox/auth.json` | Existing; tighten perms |
| Setup flag | `/etc/minebox/setup_complete` | Existing |
| Runtime state | `/var/lib/minebox/` (target) | Generated; not secrets |
| Logs | journald + `/var/log/...` | Rotate; redact |
| Backups | configurable under `/opt/minecraft/backups` (typical) | Retention policy |
| Example config in repo | `config/minebox.example.toml` (target Checkpoint 2) | No passwords |

**Separate:**

1. **User settings** — name, RAM, schedules, UI prefs.  
2. **Hardware profile** — GPIO map, fan thresholds, display resolution.  
3. **Secrets** — admin hash, Wi‑Fi PSKs, RCON password, tunnel keys.  
4. **Runtime state** — PIDs, caches, setup progress, OTA staging.

---

## 7. Hardware abstraction

```python
# Conceptual API (Checkpoint 2+)
class HardwareProfile(Protocol):
    def read_left_button(self) -> bool: ...
    def read_right_button(self) -> bool: ...
    def read_encoder_delta(self) -> int: ...
    def read_encoder_press(self) -> bool: ...
    def set_left_led(self, on: bool) -> None: ...
    def set_right_led(self, on: bool) -> None: ...
    def read_cpu_temperature_c(self) -> float: ...
    def set_fan(self, state: FanState) -> None: ...
    def request_shutdown(self) -> None: ...
    def request_reboot(self) -> None: ...
    def health(self) -> HardwareHealth: ...
```

| Profile | Purpose |
|---------|---------|
| `raspberry_pi5` | Production Pi 5 + front panel PCB |
| `mock` | Desktop/CI; keyboard simulates encoder/buttons |
| `cm5` | Placeholder; methods raise `NotImplementedError` with clear message |

**Pin source of truth:** single config file (e.g. `config/hardware/pi5.toml`) populated from `docs/v1/Hardware_Pinout.md`. Unresolved pins must not be invented in code paths that claim production readiness.

**Debounce:** edge + hold timing centralized in HAL (today partially in `gpio_buttons.py`).

---

## 8. Error flow

```
Hardware / Minecraft / Network fault
        │
        ▼
Backend classifies → ErrorRecord { id, user_message, action, log_ref }
        │
        ├──► journald (structured, no secrets)
        ├──► Display Errors screen
        └──► Web recent events / alerts
```

User-facing text must be understandable; include an **error identifier** for log correlation. UI and web must recover if backend restarts (retry + reconnect).

---

## 9. Startup order

```
1. sysinit / filesystem / networking core
2. minebox-network prerequisites (hostapd/dnsmasq/nft as designed)
3. minebox-backend (After=network-online.target is optional; SoftAP must not wait on internet)
4. minebox-minecraft (optional auto-start; After=backend if health checks needed)
5. minebox-display (After=backend; Wants=backend; retry API until ready)
6. minebox-captive (if separate)
```

**Do not** use arbitrary long `sleep` as the primary dependency mechanism; use systemd `After=` / `Wants=` / socket activation where practical. Short bounded retries in display for API readiness are OK.

---

## 10. Shutdown order

```
1. User confirms Power → Shutdown (display or web)
2. Backend: stop accepting destructive concurrent ops
3. MinecraftManager: graceful stop (save-all, stop); wait for clean exit
4. Flush backups only if explicitly requested earlier (not mid-shutdown unless configured)
5. Display exits kiosk
6. systemctl poweroff / reboot via privileged path
```

Unexpected power loss: Minecraft + FS journaling; document recovery; avoid corrupt restore from partial backup.

---

## 11. Networking model (logical)

| Role | Selection | Behavior |
|------|-----------|----------|
| SoftAP radio | Prefer USB Wi‑Fi (stable ID), fallback onboard | SSID from config; `192.168.4.0/24`; DHCP DNS = SoftAP only |
| Client radio | Remaining Wi‑Fi / Ethernet | Optional internet; failure must not kill SoftAP |
| Dashboard | All interfaces, port 8080 (+ captive :80) | Local always |
| Minecraft | Port from server.properties (often 25565) | Reachable from SoftAP + LAN |

Firewall: expose only required ports. Details: `docs/v1/Networking.md` (Checkpoint 6).

---

## 12. Remote access

**Provider interface**, disabled by default:

- No automatic public exposure of dashboard or Minecraft.
- Preferred: tunnel/VPN style; explicit owner setup; removable.
- Audit existing Tailscale path before adding a second system.

---

## 13. Package layout (evolutionary target)

Preserve live `app/` imports during migration; introduce packages gradually:

```
minebox/                    # or continue app/ with subpackages
  backend/                  # FastAPI routes, auth, orchestration
  web/                      # static dashboard assets
  display/                  # kiosk UI
  hardware/                 # HAL + profiles
  minecraft/                # manager + providers (vanilla/paper/forge)
  networking/               # status, wifi, hotspot helpers
  updates/
  backup/
  system/                   # temp, storage, power
  shared/
tests/
config/
```

Today’s `app/` maps onto this without a big-bang move in Checkpoint 1.

---

## 14. Compatibility constraints

- Keep dual-radio SoftAP + client model working (already battle-tested).
- Keep Forge/Paper/Vanilla install paths unless provider interface wraps them.
- Keep OTA `scripts/update.sh` behavior until Checkpoint 7 replaces it safely.
- Outer `C:\MineBox-OS\minebox\` tree is **legacy**; do not treat as runtime source of truth.

---

## 15. Related documents

- [Repository_Audit.md](Repository_Audit.md)
- [Implementation_Plan.md](Implementation_Plan.md)
- Hardware pinout, Networking, Test Plan — later checkpoints
