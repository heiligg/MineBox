# MineBox OS 1.3.1

MineBox is a hardware-first Minecraft server appliance interface designed for a rotary encoder, encoder press, left/back button, and right/quick-actions button.

## Install

Run the installer once from the extracted folder:

```bash
sudo bash install.sh
```

Then log out and back in once, and launch:

```bash
cd /opt/minebox
python3 main.py
```

The installer configures all required ownership, shared-group access, default ACLs when available, the Minecraft service umask, scheduled maintenance, and narrowly limited password-free service controls. MineBox should not request a sudo password during normal use.

## Physical buttons (until encoder)

- Short Left / Right: move like the encoder (on the dashboard, a short press opens the menu)
- Hold Left (~0.45s): Back / Exit
- Hold Right (~0.45s): Confirm / Select (inside menus only — not used to open the menu)

Pins: Left GPIO17 (header pin 11), Right GPIO27 (header pin 13), GND header pin 9.

## Development keyboard mapping

- Up/Down: rotate encoder (same as short L/R)
- Enter: press encoder (same as hold Right)
- Left: back/cancel (same as hold Left)
- Right: quick actions (keyboard only for now)

The dashboard is status-only and does not use letter shortcuts.
