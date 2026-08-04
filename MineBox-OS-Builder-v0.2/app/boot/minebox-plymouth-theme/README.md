# MineBox boot splash (prepared assets)

Physical boot/splash validation requires a Raspberry Pi image build. These files prepare the integration path.

## Install (on appliance image)

1. Copy this directory to `/usr/share/plymouth/themes/minebox/`
2. `plymouth-set-default-theme -R minebox` (or set `Theme=minebox` in `/etc/plymouth/plymouthd.conf`)
3. Rebuild initramfs (`update-initramfs -u`)
4. Optional quiet boot: add `quiet splash` to kernel cmdline; keep a recovery path without splash by holding Shift / using tty recovery docs

## Recovery

Curses UI remains on `tty1` via `minebox-ui.service` when graphical mode is not used or fails. Critical recovery text must not be permanently hidden — disable splash from recovery media if needed.

## Status

Assets are placeholders (solid color + text). Final artwork needs owner approval.
