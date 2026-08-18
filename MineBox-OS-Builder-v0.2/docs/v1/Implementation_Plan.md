# MineBox Implementation Plan — Prototype v1.0

**Status:** Checkpoint 8 complete (release package; software validated; image/hardware honesty in manifest)  
**Date:** 2026-08-03  
**Rule:** Preserve working features; stage independently testable work; no big-bang rewrite.

Companion docs: [Repository_Audit.md](Repository_Audit.md) · [Architecture.md](Architecture.md)

---

## Guiding principles

1. Audit before modify; claim “works” only after tests.
2. Do not invent GPIO; unresolved pins stay mock/unresolved until PCB/docs confirm.
3. Prefer repair/refactor of `MineBox-OS-Builder-v0.2/app` over replacing it.
4. Each checkpoint ends with: tests run, plan updated, files changed list, unresolved issues.
5. Installation + rollback path maintained at every installer change.

---

## Current baseline (from audit)

| Area | Classification |
|------|----------------|
| FastAPI dashboard + Minecraft manager | PARTIAL → WORKING core |
| SoftAP dual-radio + captive | WORKING (doc drift) |
| tty1 curses UI + dual buttons | WORKING (fallback; graphical is primary when enabled) |
| Graphical 800×480 kiosk | WORKING (Chromium + `/display`; encoder mock until pinout) |
| Thermal / fan | PARTIAL (platform path; GPIO fan NOT_CONFIGURED) |
| HAL / CM5 | PARTIAL (mock+Pi5+CM5 stub; encoder/LED/fan NOT_CONFIGURED) |
| Central config | WORKING (CP2 TOML + validation) |
| Auth / first-boot | WORKING (Argon2id sessions, wizard, gating) |
| Automated tests | PARTIAL (CP2–4 unit/API tests; physical matrix remains) |
| pi-gen `check-project.sh` | WORKING (channel 11 + no-resolv) |
| Outer `minebox/` tree | ARCHIVED under `archive/legacy/` |

---

## Checkpoint overview

| CP | Focus | Exit criteria (summary) |
|----|--------|-------------------------|
| **1** | Audit + architecture + this plan | Three docs exist; no rewrite started |
| **2** | Backend foundation, config, mock HAL, state model | Config validates; mock HAL; clear Minecraft states |
| **3** | Minecraft, backups, monitoring | Lifecycle + backup/restore safe; metrics |
| **4** | Web dashboard, auth, first-boot | Session security; wizard completable on SoftAP |
| **5** | Display UI, encoder, hardware | 800×480 kiosk; encoder nav; buttons via HAL |
| **6** | Networking, remote-access interface | Hotspot docs + stable iface roles; remote off by default |
| **7** | Installer, systemd, update/recovery | Idempotent install; rollback notes |
| **8** | Tests, docs, release package | Test plan executed; `releases/MineBox_OS_Prototype_v1.0/` |

---

## Checkpoint 1 — Repository audit ✅

### Deliverables

- [x] `docs/v1/Repository_Audit.md`
- [x] `docs/v1/Architecture.md`
- [x] `docs/v1/Implementation_Plan.md`

### Acceptance criteria

- [x] Subsystems classified (WORKING / PARTIAL / STUB / BROKEN / NOT IMPLEMENTED / CANNOT VERIFY)
- [x] GPIO conflict / missing pinout documented without inventing pins
- [x] No large rewrite or release packaging started

### Tests

- Document review only (no code change required).

### Unresolved (carry forward)

- Confirm Adafruit 5880 + LED + fan GPIO from PCB/KiCad (not in repo).
- Confirm illuminated button default actions for v1 product UX.
- Resolve `check-project.sh` vs hostapd channel 11 / dnsmasq `no-resolv`.
- Owner: retire or archive outer `C:\MineBox-OS\minebox\` vs Builder.

---

## Checkpoint 2 — Backend foundation, configuration, mock hardware, state model ✅

### Work

1. Introduce `config/minebox.example.toml` (+ hardware profile section) matching Architecture separation (user / hardware / secrets / runtime).
2. Startup config validation with readable errors.
3. Formal Minecraft state enum aligned with product spec (`NOT_INSTALLED` … `ERROR` / `CRASHED`); no false RUNNING from PID alone.
4. Hardware HAL: `mock`, `raspberry_pi5` (buttons from config only), `cm5` placeholder.
5. Debounce helpers in HAL; diagnostic API `/api/v1/hardware/diag`.
6. Centralize GPIO numbers in `hardware.toml`; encoder/LED/fan `NOT_CONFIGURED`.
7. Repair `check-project.sh` for channel 11 + required `no-resolv`.
8. Archive legacy `minebox/` + stale docs under `archive/`.

### Acceptance criteria

- [x] Example config documents all required keys; no secrets committed.
- [x] Invalid config fails startup with clear message.
- [x] Mock HAL usable in unit tests on Windows/Linux desktop.
- [x] Minecraft state machine documented and reflected in API status.
- [x] Pi GPIO for left/right buttons loaded from config (defaults: GPIO17 / GPIO27).
- [x] Encoder/LED/fan pins: `NOT_CONFIGURED` (not invented).
- [x] `check-project.sh` matches supported hotspot configuration.

### Tests

- Config validation unit tests.
- Mock button/encoder event tests.
- State transition unit tests (happy path + illegal transitions).

### Preserve

- Existing FastAPI routes and OTA layout under `/opt/minebox`.

---

## Checkpoint 3 — Minecraft management, backups, system monitoring ✅

### Work

1. Provider interface (Paper/Vanilla SUPPORTED; Forge/Fabric EXPERIMENTAL).
2. Lifecycle manager + health evidence + operation coordinator.
3. Backup save-off/on, checksum, retention sole-backup guard; restore confirm + rollback.
4. Crash history + loop protection; systemd StartLimitBurst.
5. Thermal hysteresis; safe shutdown coordination.
6. Docs + expanded automated tests.

### Acceptance criteria

- [x] State model covers start/stop/restart/backup/error/crash (update path reserved).
- [x] Backup/restore flows match product rules; tests with mock world dir.
- [x] Temperature API + hysteresis unit tests.
- [x] Fan GPIO NOT_CONFIGURED; platform/thermal reporting without crash.

### Tests

- 57 unittest cases (1 optional FastAPI skip) covering providers, lifecycle, backups, thermal, shutdown, RCON safety, plus Checkpoint 2 suite.

### Preserve

- Forge/Paper/Vanilla/Fabric install paths; RCON rate limits; existing API route shapes.

---

## Checkpoint 4 — Web dashboard, authentication, first-boot ✅

### Work

1. First-run admin setup (no default universal password after setup).
2. Password hashing (Argon2id), secure cookies, CSRF (`X-CSRF-Token`), login rate limit.
3. Close unauthenticated control planes post-setup (network/system/files).
4. Dashboard areas: Home, Server, Backups, Files, Network, System metrics, Settings foundation.
5. First-boot wizard over SoftAP without internet; persist setup completion + resumable wizard.
6. Factory reset with world-preservation default + explicit confirm for wipe.
7. Redact secrets from logs; restrict console commands; privileged helpers via sudoers.

### Acceptance criteria

- [x] Fresh image: wizard required; after setup, privileged APIs need auth.
- [x] SoftAP-only first boot completable (no internet required).
- [x] Files/backup path traversal rejected (CP3 + CP4 suite).
- [x] OpenAPI/docs disabled in production unless explicitly enabled.
- [x] CSRF on state-changing authenticated requests; login rate limit.
- [x] Destructive actions require confirmation tokens/fields.
- [x] Route security inventory documented; FastAPI non-root model documented.
- [x] Checkpoints 5–8 not claimed complete.

### Tests

- `tests/test_auth_cp4.py`, `tests/test_route_security_cp4.py`, plus prior CP2–3 suite.

### Preserve

- Existing UI polish, Minecraft console UX, and curses display UI.

### Unresolved (carry forward)

- Graphical 800×480 kiosk (CP5).
- OS password automation depends on image sudoers + helper present; deferred path is honest when unavailable.
- Dedicated System power UI polish can expand later; API already protected.

---

## Checkpoint 5 — Display UI, encoder navigation, hardware integration ✅

### Work

1. Chromium kiosk + dedicated `/display` UI at 800×480 (curses retained as fallback).
2. Screens: Home, Server, Details, Backups, Network, System, Power, Confirm, Setup, Degraded, Diagnostics.
3. Central action map; encoder/button events via HAL bridge (mock when encoder NOT_CONFIGURED).
4. Loopback display-token trust model for scoped actions.
5. `minebox-display.service` + kiosk launch scripts; Plymouth theme prepared (not physically validated).
6. Desktop dev launcher `app/scripts/minebox_display_dev.py`.
7. LEDs remain NOT_CONFIGURED (not invented).

### Acceptance criteria

- [x] Graphical 800×480 UI exists; no touchscreen required.
- [x] Mock encoder/button navigation works; no invented encoder GPIO.
- [x] Required screens + visible focus + destructive confirmations.
- [x] Degraded mode on backend loss; local trust model documented.
- [x] Kiosk unit + crash restart limits; curses fallback remains.
- [x] Dev mode + tests + docs; CP6–8 not claimed.

### Tests

- `tests/test_display_cp5.py` plus prior suite.

### Preserve

- Curses `minebox-ui.service` / `main.py` recovery path.
- Dual-button short/hold defaults (prev/next, back/select).

### Unresolved (carry forward)

- Physical HDMI/Chromium validation on Pi hardware.
- Real encoder GPIO after PCB verification.
- Final splash artwork approval.

---

## Checkpoint 6 — Networking and hotspot; remote-access interface ✅

### Work

1. `docs/v1/Networking.md` (+ Hotspot/Firewall/Roles/Sharing/Recovery/Remote docs).
2. Stable role detection via MAC/USB/sysfs + overrides (`networking.roles`).
3. Central `networking.state.snapshot()` for web/display/support.
4. Default-deny nftables generator + optional internet sharing.
5. Tailscale provider with enable/disable/exposure; off by default.
6. Recovery burst limits; support-bundle redaction.

### Acceptance criteria

- [x] Roles not name-only; hotspot logical without uplink; sharing optional.
- [x] Firewall blocks WAN-style exposure / RCON; Tailscale optional + auth still required.
- [x] Remote Minecraft exposure explicit and off by default.
- [x] Tests + docs; CP7–8 not claimed.

### Tests

- `tests/test_network_cp6.py` (+ prior suite). Manual dual-radio still needs Pi hardware.

### Preserve

- hostapd/dnsmasq/captive SoftAP behavior; channel 11; `no-resolv`.

### Unresolved (carry forward)

- Physical dual-radio validation on Raspberry Pi hardware.
- Image package install of Tailscale binary (owner enable still required).

---

## Checkpoint 7 — Installer, systemd, update/recovery

### Work

1. Idempotent installer: packages, `minebox` user, dirs, perms, units, kiosk, network, validate.
2. Uninstall/dev-reset preserving user data by default.
3. Systemd ordering per Architecture (rename units optionally with aliases).
4. Safe update: version, integrity, config backup, preserve worlds, restart subset, health-check rollback.
5. Prototype updater limitations clearly documented.
6. Recovery doc for backend/display/network/MC crash loop/full disk/corrupt config/failed update.
7. Fix pi-gen stage consistency with live configs.

### Acceptance criteria

- [x] Installer safe to re-run; clear failures.
- [x] Units start in documented order without long sleep hacks as primary sync.
- [x] Update dry-run / rollback path documented; prototype limits honest.
- [x] Recovery procedures use real paths/commands.

### Tests

- `tests/test_install_cp7.py` (sudoers, render dry-run, unit ordering, validate script).
- Unit file dependency review via automated assertions.
- Physical image flash remains a manual matrix item (not claimed here).

---

## Checkpoint 8 — Tests, documentation, release packaging

### Work

1. Expand automated suite (config, auth, traversal, MC states, backup, HAL mock, encoder, thermal, network parse, API perms).
2. Integration mode without real GPIO/Minecraft.
3. Write all `docs/v1/*.md` listed in product order using **implemented** commands only.
4. `docs/v1/Test_Plan.md` + physical tests.
5. `docs/v1/Known_Limitations.md`, `Release_Checklist.md`.
6. `releases/MineBox_OS_Prototype_v1.0/` + `.tar.gz` + SHA-256; no secrets/worlds/caches.

### Acceptance criteria

- [x] Test plan executed; failures triaged.
- [x] Release archive builds clean; checksum published.
- [x] Docs match repo reality.
- [x] Known limitations honest (encoder pins, CM5, updater prototype, etc.).

### Tests

- Full automated suite + `tests/test_release_cp8.py`.
- Physical matrix: [Prototype_Hardware_Test_Plan.md](Prototype_Hardware_Test_Plan.md) (manual; not claimed automated).

---

## Phase → Checkpoint mapping (product phases)

| Product phase | Primary checkpoint |
|---------------|-------------------|
| 1 Audit | CP1 |
| 2 Architecture | CP1 |
| 3 Central config | CP2 |
| 4 HAL | CP2 (+ CP5 physical) |
| 5 Display UI | CP5 |
| 6 Web dashboard | CP4 |
| 7 Minecraft | CP3 |
| 8 Networking | CP6 |
| 9 Remote access | CP6 |
| 10 Fan/thermal | CP3 |
| 11 Backup/restore | CP3 |
| 12 First-boot | CP4 |
| 13 Installer/systemd | CP7 |
| 14 Updates/recovery | CP7 |
| 15 Logging/diagnostics | CP2–7 incremental; CP8 bundle |
| 16 Testing | Each CP + CP8 |
| 17 Documentation | Incremental + CP8 |
| 18 Release | CP8 |

---

## Owner approval needed before later checkpoints

1. **PCB pinout** for encoder (Adafruit 5880), left/right LEDs, fan control (on/off vs PWM).
2. **Default illuminated button actions** for v1 (keep current short/hold nav model vs product remapping).
3. **Display stack:** keep curses tty1 vs new graphical kiosk (Chromium/Qt/etc.) for 800×480.
4. **Default admin/SSH/hotspot credentials policy** for images (must change on first boot?).
5. **Archive/delete** obsolete outer `minebox/` tree and stale docs (`INTERNET-SHARING.md`, updater-v2).
6. **Minecraft providers in v1:** Forge (current) + Paper/Vanilla only, or Forge-primary?
7. **Remote access:** keep Tailscale as sole provider?

---

## Change log (this plan)

| Date | Checkpoint | Notes |
|------|------------|-------|
| 2026-08-01 | CP1 | Initial plan from repository audit; no implementation rewrite |
| 2026-08-01 | CP2 | Config, secrets, HAL, states, foundation API, check-project fix, archive, tests |
| 2026-08-01 | CP3 | Providers, lifecycle, health, backups/restore, thermal, crash, shutdown, tests/docs |
| 2026-08-01 | CP7 | Idempotent install.sh, pi-gen Chromium/X/Plymouth, SoftAP render, recovery docs, CP7 tests |
| 2026-08-03 | CP8 | Version centralization, release audit/package, first-boot check, hardware plan, CP8 tests |

### Files produced in Checkpoint 1

- `docs/v1/Repository_Audit.md`
- `docs/v1/Architecture.md`
- `docs/v1/Implementation_Plan.md`

### Checkpoint 2 deliverables (summary)

- `config/minebox.example.toml`, `hardware.example.toml`, `secrets.example.env`
- `app/core/{minebox_config,secrets_store,bootstrap,states,state_service}.py`
- `app/hardware/*`, `app/networking/remote_access.py`, `app/api/routes/foundation.py`
- `tests/*`, `docs/v1/{Configuration,Security_Model,State_Models,Hardware_Pinout,Known_Limitations}.md`
- `archive/` legacy tree + stale docs

### Tests run (CP2)

- `python -m unittest discover -s tests -v` from `MineBox-OS-Builder-v0.2` with `PYTHONPATH=app`
- `check-project.sh` (bash) when available

### Unresolved issues (open)

- PCB source verification for buttons/encoder/LEDs/fan.
- Physical SD flash + quiet-boot validation (CP7 prepared; hardware pending).
- Tailscale binary packaging optional (CP6 provider ready).
- Checkpoint 8 (release packaging / expanded docs) not started.
