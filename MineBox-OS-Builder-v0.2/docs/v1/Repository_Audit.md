# MineBox OS Prototype v1.0 — Repository Audit

**Checkpoint:** 1 (audit only)  
**Date:** 2026-08-01  
**Scope:** `C:\MineBox-OS` with primary product tree `MineBox-OS-Builder-v0.2/`  
**Method:** Static code and config inspection. Hardware runtime not re-verified in this checkpoint.  
**Rule:** GPIO assignments are taken only from repository sources; no invented pins.

---

## 1. Repository layout

| Path | Role |
|------|------|
| `MineBox-OS-Builder-v0.2/` | **Canonical appliance** (app, pi-gen stage, OTA target) |
| `MineBox-OS-Builder-v0.2/app/` | Runtime application (`/opt/minebox` after install/OTA) |
| `MineBox-OS-Builder-v0.2/pi-gen/stage-minebox/` | Image customization stages |
| `MineBox-OS-Builder-v0.2/config/minebox-pi5.conf` | pi-gen build configuration |
| `minebox/` (repo root) | **Legacy** pre-dashboard tree — obsolete for v1 |
| `.github/workflows/` | Image CI (blocked while `check-project.sh` fails) |

**OTA source of truth:** GitHub `heiligg/MineBox`, `app_subdir=MineBox-OS-Builder-v0.2/app` → `/opt/minebox`.

---

## 2. Subsystem inventory

### 2.1 Operating system / image build

| Field | Detail |
|-------|--------|
| **Status** | PARTIAL |
| **Sources** | `build.sh`, `check-project.sh`, `config/minebox-pi5.conf`, `pi-gen/stage-minebox/*`, `.github/workflows/build-minebox-image.yml` |
| **Works** | Stage list `stage0–2 + stage-minebox`; installs app to `/opt/minebox`; creates users/`minecraft` ACLs; enables API, UI, hotspot, captive, Minecraft unit, maintenance timer; dual-radio SoftAP stage |
| **Incomplete** | `check-project.sh` currently **fails** (expects hostapd `channel=6`, forbids dnsmasq `no-resolv`; live configs use `channel=11` + `no-resolv`) — blocks `./build.sh` and CI. Nested `pi-gen/.../files/minebox/` is a stale embed overwritten by rsync. Dual `02-*` stages rely on alpha order |
| **Risks** | Build gate broken; doc/code drift (SSH “disabled” vs enabled); default password `minebox`/`minebox` baked into image |
| **Action** | **Repair** check-project assertions; **refactor** stage numbering; **preserve** pi-gen flow |

### 2.2 Installer / OTA / rollback

| Field | Detail |
|-------|--------|
| **Status** | WORKING (code) / CANNOT VERIFY (full image + OTA soak) |
| **Sources** | Image: pi-gen chroots. OTA: `services/updates.py`, `scripts/minebox_update_apply.py`, `minebox-update.service`. Legacy: `app/install.sh`, root `minebox/install.sh`, `scripts/minebox_updater.py` |
| **Works** | OTA clone → validate → swap `/opt/minebox` ↔ `/opt/minebox.previous` → healthcheck → auto-rollback; dnsmasq-safe restart helpers; hotspot helper install on update |
| **Incomplete** | No manual rollback API; `app/install.sh` does not install full image unit set (legacy curses path); `UPDATER-V2.md` / `minebox_updater.py` superseded but still present |
| **Risks** | Operators may run wrong installer; stale updater docs |
| **Action** | **Preserve** `minebox_update_apply.py`; **replace** obsolete updater docs; align or retire `install.sh` |

### 2.3 Systemd services

| Unit | Status | ExecStart (summary) |
|------|--------|---------------------|
| `minebox-api.service` | WORKING (unit) | `minebox_api_run.py` as user `minebox` |
| `minebox-ui.service` | WORKING (unit) | `main.py` on `/dev/tty1` |
| `minebox-captive.service` | WORKING (unit) | `minebox_captive.py` as **root** (port 80) |
| `minecraft.service` | PARTIAL | `python3 -m services.launcher`; restart loop risk if no active server |
| `minebox-maintenance.timer/service` | WORKING | periodic maintenance |
| `minebox-update.service` | WORKING | oneshot OTA apply (not boot-enabled) |
| `minebox-firstboot.service` | WORKING | oneshot first-boot helper |
| `hostapd` / `dnsmasq` / `nftables` | WORKING (config) | SoftAP + DHCP/DNS + NAT |
| `minebox-network.service` | STUB/LEGACY | NM hotspot guard — disabled on image |
| `minebox.service` | PARTIAL | Duplicate of UI without TTY — legacy install path |

### 2.4 Backend API

| Field | Detail |
|-------|--------|
| **Status** | WORKING |
| **Sources** | `app/api/server.py`, `app/api/routes/*`, `app/core/security.py`, `app/services/*` |
| **Works** | FastAPI dashboard API; session auth (scrypt); Minecraft/network/backups/files/players/mods/join/updates/system routes; health endpoint |
| **Incomplete** | No CSRF tokens; no login rate limit; OpenAPI `/docs` public; network APIs public during incomplete setup; version strings drift |
| **Risks** | Session cookie `https_only=False`; first-boot network trust boundary; known default RCON password in `config.py` |
| **Action** | **Preserve** surface; **repair** auth hardening for Prototype v1 |

### 2.5 Web dashboard

| Field | Detail |
|-------|--------|
| **Status** | WORKING |
| **Sources** | `app/web/templates/*`, `app/web/static/js/*`, `api/routes/dashboard.py`, `setup.py`, `tls.py` |
| **Works** | Home/status, console, players, files, mods, network, join, backups, settings, security (password + TLS), updates, fan test; first-boot `/setup` + admin creation; optional self-signed TLS gateway |
| **Incomplete** | No true responsive “graphical product” redesign for 800×480 kiosk (web is desktop-oriented); self-signed UX friction; empty `partials/` |
| **Risks** | Operators bookmark HTTPS while TLS off (historical “Failed to fetch”) |
| **Action** | **Preserve**; **refactor** UI for encoder/hotspot-first polish in later checkpoints |

### 2.6 On-device display UI

| Field | Detail |
|-------|--------|
| **Status** | PARTIAL |
| **Sources** | `app/main.py`, `app/menu.py`, `app/gpio_buttons.py`, `app/display.py` (unused by curses path), `minebox-ui.service` |
| **Works** | Fullscreen curses UI on tty1 (getty masked); menus for server/network-ish ops/system/power; two-button stand-in for encoder (short = navigate, hold L = back, hold R = select; dashboard tap opens menu) |
| **Incomplete** | No Waveshare 800×480 panel config; no boot splash; no brightness driver; screen timeout setting saved but unused; no Chromium/kiosk web UI; encoder not implemented |
| **Risks** | Curses on HDMI may not match “finished appliance” look; ROADMAP still lists button pins as unfinished while code has provisional pins |
| **Action** | **Preserve** curses + button bridge; **replace/extend** with 800×480 graphical UI in Checkpoint 5; HAL before encoder |

### 2.7 Hardware / GPIO / encoder / LEDs

| Field | Detail |
|-------|--------|
| **Status** | WORKING (buttons + Seesaw I²C encoder) / NOT_CONFIGURED (LEDs, fan GPIO) |
| **Sources** | `gpio_buttons.py`, `scripts/button_test.py`, `button_monitor.py`, `config/hardware.example.toml`, `docs/v1/Hardware_Pinout.md` |
| **Works** | Debounced dual buttons via gpiozero; UI injection of curses keys; diagnostic scripts |
| **GPIO from repo:** | Left **GPIO17 / header pin 11**; Right **GPIO27 / header pin 13**; INT **GPIO22 / header pin 15**; GND **header pin 9**; 5 V LEDs **header pin 4**; active-low with PCB 10 k pull-ups |
| **Missing** | LED illumination GPIO; KiCad/PCB files (**none in repository**); CM5 profile |
| **Conflicts** | Older software used GPIO23/17 and INT GPIO24. Current map is GPIO17/27/22. Fan uses Pi 5 `FAN_PWM` / cooling_fan. |
| **Action** | LED/fan GPIO remain unset until pinout is provided |

### 2.8 Fan / thermal

| Field | Detail |
|-------|--------|
| **Status** | WORKING (code) / CANNOT VERIFY (hardware) |
| **Sources** | `services/monitoring.py`, `scripts/minebox_fan_test.py`, `api/routes/system.py` |
| **Works** | CPU temp, fan RPM/PWM discovery, dashboard fan test via `pinctrl FAN_PWM`, alerts ≥80°C |
| **Incomplete** | No configurable hysteresis policy UI; relies on firmware/platform cooler |
| **Action** | **Preserve**; add threshold config in Phase 10 |

### 2.9 Networking / hotspot

| Field | Detail |
|-------|--------|
| **Status** | WORKING (code) / CANNOT VERIFY (full soak) |
| **Sources** | `services/network.py`, `services/hotspot/*`, `minebox_captive.py`, `pi-gen/.../02-dedicated-hotspot/*`, nftables, dnsmasq, hostapd |
| **Works** | Dedicated SoftAP on onboard radio (`wlan0`); client uplink on USB Wi-Fi (`wlan1`) or Ethernet; DHCP `192.168.4.0/24`; Pi DNS + captive portal `:80`; NAT internet sharing when uplink present; mDNS `minebox.local`; dual-radio NM unmanaged wlan0 |
| **Incomplete** | Interface names still largely `wlan0`/`wlan1` (not fully stable-by-MAC selection); `INTERNET-SHARING.md` obsolete (describes NM shared); default PSK `mineboxsetup` |
| **Risks** | Windows SoftAP stickiness historically fragile (mitigations present); SSH allowed on hotspot interface |
| **Action** | **Preserve** hostapd stack; **repair** docs; add first-boot hotspot password change |

### 2.10 Remote access

| Field | Detail |
|-------|--------|
| **Status** | PARTIAL |
| **Sources** | `services/join_access.py`, UPnP/join routes, Avahi |
| **Works** | Local join helpers, Avahi `_minecraft._tcp` / `_http._tcp`, optional UPnP path in join UI |
| **Incomplete** | No disabled-by-default secure tunnel/VPN provider interface as specified for Prototype remote access |
| **Action** | **Preserve** local join; **add** remote-access provider interface (Phase 9) without exposing ports by default |

### 2.11 Minecraft server management

| Field | Detail |
|-------|--------|
| **Status** | WORKING |
| **Sources** | `minecraft.py`, `launcher.py`, `servers.py`, `downloads.py`, `installer.py`, `rcon.py`, `mods.py`, `players.py` |
| **Works** | Create/select servers; vanilla/paper/fabric/forge/neoforge; start/stop/restart via systemd; RCON with Forge hardening; player ops; mods (Modrinth/CF/URL); multi-server registry under `/opt/minecraft/servers` |
| **Incomplete** | Formal state machine enum not explicit; default RCON password constant; `minecraft.service` may flap without jar/active server |
| **Action** | **Preserve**; add explicit state model + random RCON at create (Phase 7) |

### 2.12 Backups

| Field | Detail |
|-------|--------|
| **Status** | WORKING |
| **Sources** | `services/backups.py`, API routes, maintenance hooks |
| **Works** | Create/list/download/restore/delete; retention; blocks unsafe restore while running (guards present) |
| **Incomplete** | Save-flush/`save-off` sequencing should be soak-tested; no pre-restore automatic “current world” safety archive guarantee documented as always-on |
| **Action** | **Preserve**; tighten Phase 11 acceptance tests |

### 2.13 Authentication / first boot

| Field | Detail |
|-------|--------|
| **Status** | WORKING / PARTIAL |
| **Sources** | `services/auth.py`, `api/routes/auth.py`, `setup.py`, `minebox-firstboot`, `/setup` wizard |
| **Works** | First admin password setup; session cookies; setup wizard for initial appliance config |
| **Incomplete** | OS user password still default; hotspot PSK not forced-rotated; timezone/EULA flows may be incomplete vs Phase 12 checklist; factory reset not fully specified |
| **Action** | **Repair** first-boot to force credential rotation |

### 2.14 Updates / recovery

| Field | Detail |
|-------|--------|
| **Status** | WORKING (OTA apply) / PARTIAL (docs & recovery UX) |
| **Sources** | `updates.py`, `minebox_update_apply.py`, captive/hotspot restore helpers |
| **Works** | Channelled Git OTA with rollback on health failure |
| **Incomplete** | Signed release packages not required yet; recovery playbook incomplete; check-project blocks image rebuild |
| **Action** | Document Prototype limitations; add Recovery guide in Phase 14/17 |

### 2.15 Logging / diagnostics

| Field | Detail |
|-------|--------|
| **Status** | PARTIAL |
| **Sources** | journald units, `services/logs.py`, console mirror, monitoring |
| **Works** | Journal per unit; dashboard console; some structured append |
| **Incomplete** | No unified support-bundle export with redaction; inconsistent log roots |
| **Action** | Add Phase 15 support bundle |

### 2.16 Tests

| Field | Detail |
|-------|--------|
| **Status** | NOT IMPLEMENTED / STUB |
| **Sources** | No substantial automated test suite found for API/auth/Minecraft state |
| **Action** | Implement Phase 16 from plan |

### 2.17 Documentation

| Field | Detail |
|-------|--------|
| **Status** | PARTIAL / BROKEN in places |
| **Sources** | `README-FIRST.md`, `docs/ROADMAP.md`, `INTERNET-SHARING.md`, `UPDATER-V2.md`, `FRIENDLY-HOSTNAME.md`, `app/README.md` |
| **Works** | High-level appliance intent; mDNS notes; hardware deferral list |
| **Broken/stale** | SSH disabled claim; NM sharing docs; updater-v2 vs apply script; version drift |
| **Action** | Replace with `docs/v1/*` set (this checkpoint starts that) |

---

## 3. Obsolete / duplicate inventory

| Item | Recommendation |
|------|----------------|
| Root `minebox/` tree | Archive or delete after confirming no unique assets |
| `pi-gen/.../files/minebox/` stale embed | Generate-only via build rsync |
| `minebox_updater.py` + `UPDATER-V2.md` | Archive; point to `minebox_update_apply.py` |
| `INTERNET-SHARING.md` | Rewrite for hostapd/nftables |
| `minebox-network.service` / `network_guard.py` | Keep disabled or remove after OTA safety check |
| `*.backup*` files under `app/` | Delete from tree |
| Nested `.git` inside Builder | Resolve ownership confusion |

---

## 4. Security findings (summary)

1. Default OS password `minebox`/`minebox` on image.  
2. Default hotspot PSK `mineboxsetup`.  
3. Hardcoded RCON password `MineBoxLocalRcon` in `app/config.py`.  
4. SSH enabled with password auth; docs claim otherwise.  
5. Public OpenAPI docs; network APIs open during setup.  
6. No login rate limit / CSRF.  
7. Captive portal process runs as root.  
8. Polkit grants broad NetworkManager rights to `minebox`.  
9. Web can trigger poweroff/reboot via sudoers allowlist.

---

## 5. Classification rollup

| Subsystem | Classification |
|-----------|----------------|
| Image build pipeline | PARTIAL (gate BROKEN) |
| OTA update/rollback | WORKING (code) |
| Backend API | WORKING |
| Web dashboard | WORKING |
| Curses display UI | PARTIAL |
| Physical buttons | WORKING (provisional pins) |
| Rotary encoder | NOT IMPLEMENTED |
| LED control | NOT IMPLEMENTED |
| Fan/thermal | WORKING (code) / CANNOT VERIFY |
| Hotspot dual-radio | WORKING (code) / CANNOT VERIFY |
| Minecraft lifecycle | WORKING |
| Backups | WORKING |
| Auth / first-boot | PARTIAL |
| Remote access (secure tunnel) | NOT IMPLEMENTED |
| HAL / CM5 profile | NOT IMPLEMENTED |
| Automated tests | NOT IMPLEMENTED |
| PCB / KiCad pinout | NOT IMPLEMENTED |
| Boot splash / 800×480 kiosk | NOT IMPLEMENTED |

---

## 6. Owner decisions required

See `Implementation_Plan.md` § Owner approvals. Highest urgency:

1. LED and fan GPIO remain unset until pinout is provided.  
2. Encoder is I²C1 `0x36` with optional INT GPIO22.  
3. Accept Prototype default-credential policy (force change on first boot vs ship defaults).  
4. Choose display UI path: evolve curses vs new 800×480 graphical kiosk.  
5. Confirm whether hotspot internet sharing remains a v1 requirement (currently implemented).
