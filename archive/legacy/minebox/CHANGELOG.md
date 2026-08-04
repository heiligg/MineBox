# MineBox v1.3

- Removed all dashboard letter shortcuts.
- Dashboard is now information-only.
- Added hardware-first control model.
- Left Arrow simulates the physical Back button.
- Right Arrow simulates the physical Quick Actions button.
- Added global Quick Actions menu.
- Converted console, performance, and log browser controls to left/right hardware actions.
- Removed the dashboard quick-actions setting.
- Preserved all v1.2 server, backup, diagnostics, monitoring, and maintenance features.

# MineBox 1.2.0

- Added live CPU, memory, and Minecraft memory monitoring.
- Added performance history graphs.
- Added searchable and filterable log browser.
- Added log export to `~/.config/minebox/exports`.
- Added configuration validation checks.
- Added dashboard quick actions for start/stop, backups, and logs.
- Added automatic backup interval setting.
- Added daily scheduled restart setting.
- Added systemd maintenance timer files and installer.
- Kept all MineBox 1.1 features and the working curses interface.

## 1.3.1
- Fixed permission-denied errors in backup creation, deletion, and restoration.
- Added shared MineBox/Minecraft group ownership for `/opt/minecraft`.
- Added setgid directory permissions and optional default ACLs for future files.
- Added `UMask=0002` override for `minecraft.service`.
- Added exact password-free sudo rules for MineBox service and power actions.
- Replaced the old installer with a complete `install.sh`.
