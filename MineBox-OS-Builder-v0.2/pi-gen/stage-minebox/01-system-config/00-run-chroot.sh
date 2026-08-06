#!/bin/bash -e

mkdir -p /etc/minebox
cat >/etc/minebox/minecraft.env <<'ENV'
JAVA_MIN_RAM=-Xms1G
JAVA_MAX_RAM=-Xmx2G
ENV
chmod 0644 /etc/minebox/minecraft.env

# Boot directly into the MineBox UI on tty1; tty2 remains available for recovery.
systemctl disable getty@tty1.service || true
systemctl mask getty@tty1.service
systemctl enable minebox-firstboot.service
systemctl enable minebox-ui.service
systemctl enable minecraft.service
systemctl enable ssh.service

# Graphical kiosk when Chromium + xinit were packaged (00-install-minebox).
if [ -f /etc/systemd/system/minebox-display.service ]; then
  if command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1; then
    if command -v xinit >/dev/null 2>&1; then
      systemctl enable minebox-display.service
    fi
  fi
fi

# Reduce console noise during the appliance boot.
mkdir -p /etc/systemd/system.conf.d
cat >/etc/systemd/system.conf.d/minebox.conf <<'CONF'
[Manager]
ShowStatus=auto
DefaultTimeoutStopSec=120s
CONF

# I²C1 for Adafruit Seesaw rotary encoder (Product 5880).
for cfg in /boot/firmware/config.txt /boot/config.txt; do
  if [ -f "$cfg" ]; then
    sed -i 's/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' "$cfg" || true
    if ! grep -q '^dtparam=i2c_arm=on' "$cfg"; then
      printf '\n# MineBox: Seesaw rotary encoder (I²C1)\ndtparam=i2c_arm=on\n' >>"$cfg"
    fi
    break
  fi
done
if command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_i2c 0 || true
fi

# Preserve logs across boots but cap their disk usage.
mkdir -p /etc/systemd/journald.conf.d
cat >/etc/systemd/journald.conf.d/minebox.conf <<'CONF'
[Journal]
Storage=persistent
SystemMaxUse=200M
RuntimeMaxUse=50M
CONF
