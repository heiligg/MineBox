#!/bin/bash -e

# Remove old NetworkManager hotspot profiles and disable the legacy guard so
# only hostapd owns wlan0. Competing AP managers caused Windows clients to drop.
rm -f /etc/NetworkManager/system-connections/MineBox-Hotspot.nmconnection
rm -f /etc/NetworkManager/system-connections/MineBox-Setup.nmconnection
systemctl disable minebox-network.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/multi-user.target.wants/minebox-network.service

# Explicitly point Debian's hostapd service at the MineBox configuration.
cat >/etc/default/hostapd <<'CONF'
DAEMON_CONF="/etc/hostapd/hostapd.conf"
CONF

# Raspberry Pi OS masks hostapd after package installation until configured.
systemctl unmask hostapd.service
systemctl enable systemd-networkd.service
systemctl enable hostapd.service
systemctl enable dnsmasq.service
systemctl enable nftables.service
systemctl enable ssh.service
systemctl enable minebox-captive.service >/dev/null 2>&1 || true

# NetworkManager may still manage Ethernet or an additional Wi-Fi adapter, but
# wlan0 belongs exclusively to systemd-networkd + hostapd. Any working default
# route on another interface can be shared with hotspot clients through nftables.
systemctl enable NetworkManager.service >/dev/null 2>&1 || true

mkdir -p /etc/systemd/system/hostapd.service.d
cat >/etc/systemd/system/hostapd.service.d/minebox.conf <<'CONF'
[Unit]
After=systemd-networkd.service
Wants=systemd-networkd.service

[Service]
ExecStartPre=/usr/sbin/rfkill unblock wifi
Restart=on-failure
RestartSec=3
CONF

# dnsmasq must start after wlan0 receives 192.168.4.1.
mkdir -p /etc/systemd/system/dnsmasq.service.d
cat >/etc/systemd/system/dnsmasq.service.d/minebox.conf <<'CONF'
[Unit]
After=systemd-networkd.service hostapd.service
Wants=systemd-networkd.service
CONF

# Load routing sysctls during image creation as well as on every real boot.
sysctl --system >/dev/null 2>&1 || true

systemctl daemon-reload
