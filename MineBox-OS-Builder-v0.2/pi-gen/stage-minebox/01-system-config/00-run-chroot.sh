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

# Reduce console noise during the appliance boot.
mkdir -p /etc/systemd/system.conf.d
cat >/etc/systemd/system.conf.d/minebox.conf <<'CONF'
[Manager]
ShowStatus=auto
DefaultTimeoutStopSec=120s
CONF

# Preserve logs across boots but cap their disk usage.
mkdir -p /etc/systemd/journald.conf.d
cat >/etc/systemd/journald.conf.d/minebox.conf <<'CONF'
[Journal]
Storage=persistent
SystemMaxUse=200M
RuntimeMaxUse=50M
CONF
