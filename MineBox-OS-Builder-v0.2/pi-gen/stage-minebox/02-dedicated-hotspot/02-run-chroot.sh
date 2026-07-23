#!/bin/bash -e

# Remove any older NetworkManager hotspot profile so it cannot compete with hostapd.
rm -f /etc/NetworkManager/system-connections/MineBox-Hotspot.nmconnection
rm -f /etc/NetworkManager/system-connections/MineBox-Setup.nmconnection

# Raspberry Pi OS masks hostapd after package installation until it is configured.
systemctl unmask hostapd.service
systemctl enable systemd-networkd.service
systemctl enable hostapd.service
systemctl enable dnsmasq.service
systemctl enable ssh.service

# Make hostapd wait until wlan0 has its fixed 192.168.4.1 address.
mkdir -p /etc/systemd/system/hostapd.service.d
cat >/etc/systemd/system/hostapd.service.d/minebox.conf <<'CONF'
[Unit]
After=systemd-networkd.service
Wants=systemd-networkd.service
CONF

# Ensure wireless is not left blocked by a previous saved rfkill state.
mkdir -p /etc/systemd/system/hostapd.service.d
cat >>/etc/systemd/system/hostapd.service.d/minebox.conf <<'CONF'

[Service]
ExecStartPre=/usr/sbin/rfkill unblock wifi
CONF
