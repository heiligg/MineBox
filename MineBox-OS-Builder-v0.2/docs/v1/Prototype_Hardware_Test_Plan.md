# Prototype Hardware Test Plan — MineBox OS Prototype v1.0

**Product:** MineBox OS Prototype v1.0 (`1.0.0-prototype.1`)  
**Target:** Assembled Raspberry Pi 5 MineBox appliance  
**Status:** Manual checklist — **physical validation NOT claimed by Checkpoint 8 software packaging**

Print this page. Mark Pass / Fail / Blocked / N/A. Record observations.

---

## Severity scale

| Severity | Meaning |
|----------|---------|
| S0 | Bricks appliance / data loss risk |
| S1 | Core function unusable |
| S2 | Degraded / workaround exists |
| S3 | Cosmetic / docs |

## Common prerequisites

- Flashed MineBox image or manual install completed
- SoftAP radio + optional uplink radio as designed
- Monitor/DSI/HDMI for kiosk, or serial/SSH for headless notes
- Minecraft client on LAN for join tests
- **Do not invent encoder/LED/fan pins** — mark Blocked if `NOT_CONFIGURED`

---

### 1. SD card boot
- **Prerequisites:** Valid image on SD; Pi 5 powered
- **Steps:** Insert SD, apply power
- **Expected:** Kernel/systemd reach multi-user; no endless boot loop
- Pass / Fail | Observations | Severity if fail: **S0**

### 2. Boot splash
- **Prerequisites:** Plymouth theme installed
- **Steps:** Observe boot
- **Expected:** MineBox splash or quiet boot without panic; console recoverable
- Pass / Fail / N/A | Severity: **S3**

### 3. Kiosk launch
- **Prerequisites:** Chromium + xinit; `minebox-display` enabled
- **Steps:** Boot to graphical target
- **Expected:** `/display` at ~800×480 on local screen
- Pass / Fail / N/A | Severity: **S1**

### 4. Curses fallback
- **Prerequisites:** tty1; `minebox-ui`
- **Steps:** Disable display or switch to tty1
- **Expected:** Curses UI usable
- Pass / Fail | Severity: **S1**

### 5. Display resolution and readability
- **Steps:** Inspect kiosk UI contrast/type size
- **Expected:** Readable at 800×480; no clipped primary controls
- Pass / Fail | Severity: **S2**

### 6. Left button
- **Prerequisites:** GPIO17 (header pin 11) wired; HAL not mock-only
- **Steps:** Short press / hold per Display UI flow
- **Expected:** Back / hold actions match docs
- Pass / Fail | Severity: **S1**

### 7. Right button
- **Prerequisites:** GPIO27 (header pin 13)
- **Steps:** Short / hold
- **Expected:** Select / alternate actions match docs
- Pass / Fail | Severity: **S1**

### 8. Rotary encoder (when pinout configured)
- **Prerequisites:** Encoder GPIOs **configured and verified against PCB**
- **Steps:** Rotate CW/CCW
- **Expected:** Focus moves
- **Blocked until PCB pinout confirmed** if `NOT_CONFIGURED`
- Pass / Fail / **Blocked** | Severity: **S2**

### 9. Encoder press
- **Prerequisites:** Same as #8
- **Expected:** Activate focused control
- Pass / Fail / **Blocked** | Severity: **S2**

### 10. Button LEDs when configured
- **Prerequisites:** LED GPIOs configured
- **Blocked until pinout confirmed** if `NOT_CONFIGURED`
- Pass / Fail / **Blocked** | Severity: **S3**

### 11. Fan and temperature reporting
- **Prerequisites:** Pi thermal sysfs; Active Cooler if used
- **Steps:** Dashboard/system status temperature; fan policy
- **Expected:** Temperature readable; GPIO fan remains honest if `NOT_CONFIGURED`
- Pass / Fail | Severity: **S2**

### 12. Ethernet
- **Steps:** Cable uplink; ping gateway
- **Expected:** Address via DHCP; dashboard reachable on LAN IP
- Pass / Fail / N/A | Severity: **S1**

### 13. Uplink Wi-Fi
- **Prerequisites:** Client radio not SoftAP
- **Steps:** Join SSID via dashboard
- **Expected:** Uplink without killing SoftAP
- Pass / Fail | Severity: **S1**

### 14. USB hotspot adapter
- **Prerequisites:** Dual-radio hardware
- **Steps:** Boot with USB Wi-Fi; check roles
- **Expected:** SoftAP on intended radio; no silent wrong reassignment
- Pass / Fail / N/A | Severity: **S1**

### 15. Hotspot without internet
- **Steps:** SoftAP only; no uplink
- **Expected:** `MineBox-Setup` up; local DNS/DHCP; dashboard at `http://192.168.4.1`
- Pass / Fail | Severity: **S0/S1**

### 16. Hotspot dashboard access
- **Steps:** Phone/PC join SoftAP; open dashboard
- **Expected:** Login/setup reachable over HTTP SoftAP path
- Pass / Fail | Severity: **S1**

### 17. Local Minecraft connection
- **Prerequisites:** Server running; client on SoftAP or LAN
- **Expected:** Join world
- Pass / Fail | Severity: **S1**

### 18. Optional internet sharing
- **Prerequisites:** Uplink + sharing enabled
- **Expected:** SoftAP clients reach internet via nftables NAT; off when disabled
- Pass / Fail / N/A | Severity: **S2**

### 19. First-boot wizard
- **Steps:** Fresh image; complete `/setup`
- **Expected:** Gating until complete; no skip of required rotations
- Pass / Fail | Severity: **S1**

### 20. Credential rotation
- **Steps:** Admin, hotspot PSK, OS password, RCON paths
- **Expected:** Bootstrap PSK rejected; secrets not echoed in logs
- Pass / Fail | Severity: **S1**

### 21. Server installation
- **Steps:** Install Paper or Vanilla via UI
- **Expected:** JAR placed; EULA flow honest
- Pass / Fail | Severity: **S1**

### 22. Paper start/stop/restart
- **Expected:** Lifecycle states; confirm on stop/restart
- Pass / Fail | Severity: **S1**

### 23. Vanilla start/stop/restart
- **Expected:** Same as Paper for SUPPORTED vanilla
- Pass / Fail | Severity: **S1**

### 24. Backup
- **Expected:** Archive under `/opt/minecraft/backups`; checksum
- Pass / Fail | Severity: **S1**

### 25. Restore
- **Expected:** Confirm required; worlds restored; no path traversal
- Pass / Fail | Severity: **S0**

### 26. Safe reboot
- **Expected:** Minecraft stopped/saved; clean reboot
- Pass / Fail | Severity: **S1**

### 27. Safe shutdown
- **Expected:** Poweroff after orderly stop
- Pass / Fail | Severity: **S1**

### 28. Unexpected power-loss recovery
- **Steps:** Cut power while idle and while running (lab only)
- **Expected:** Boots; SoftAP; no infinite crash loop; worlds intact or recover via backup
- Pass / Fail | Severity: **S0**

### 29. Tailscale optional setup
- **Expected:** Disabled by default; enable with auth key; disable needs confirm
- Pass / Fail / N/A | Severity: **S2**

### 30. Remote Minecraft test
- **Prerequisites:** Tailscale or LAN path documented
- **Expected:** Join from remote client per Remote_Minecraft.md
- Pass / Fail / N/A | Severity: **S2**

### 31. Thermal soak
- **Steps:** Load server 30–60 min
- **Expected:** Temp reported; throttling/alerts per policy; no thermal panic
- Pass / Fail | Severity: **S2**

### 32. Storage-full warning
- **Steps:** Fill disk in lab (careful)
- **Expected:** Warning/status; no silent corruption claim
- Pass / Fail | Severity: **S1**

### 33. Adapter removal/reinsertion
- **Expected:** Recovery limits; SoftAP restored when possible; stale roles not silently stolen
- Pass / Fail | Severity: **S1**

### 34. Backend restart recovery
- **Steps:** `systemctl restart minebox-api`
- **Expected:** API returns; kiosk reconnects; SoftAP stays
- Pass / Fail | Severity: **S1**

### 35. Kiosk restart recovery
- **Steps:** `systemctl restart minebox-display`
- **Expected:** Display returns or curses remains; StartLimit respected
- Pass / Fail | Severity: **S2**

---

## Sign-off

| Field | Value |
|-------|-------|
| Tester | |
| Date | |
| Image / package version | |
| Hardware revision / PCB | |
| Encoder/LED/fan pinout status | NOT_CONFIGURED / Verified |
| Overall result | PASS / FAIL / PARTIAL |
| Notes | |

**Prototype v1.0 is not mass-production ready.** Passing this matrix validates a lab prototype unit, not a shipping SKU.
