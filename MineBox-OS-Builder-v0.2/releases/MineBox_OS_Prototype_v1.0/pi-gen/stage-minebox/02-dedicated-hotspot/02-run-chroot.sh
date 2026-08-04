#!/bin/bash -e

# Remove old NetworkManager hotspot profiles and disable the legacy guard so
# only hostapd owns the SoftAP interface. Competing AP managers caused clients to drop.
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
# the SoftAP iface belongs exclusively to systemd-networkd + hostapd.
systemctl enable NetworkManager.service >/dev/null 2>&1 || true

# Seed dynamic hostapd/dnsmasq/nft/networkd from templates (default wlan0 in chroot).
# Real hardware re-resolves on first boot via minebox-firstboot / render helper.
if [ -f /opt/minebox/scripts/minebox_render_hotspot_configs.py ]; then
  PYTHONPATH=/opt/minebox /usr/bin/python3 /opt/minebox/scripts/minebox_render_hotspot_configs.py --iface wlan0 \
    || true
else
  # Fallback drop-ins if app tree is unexpectedly missing the renderer.
  mkdir -p /etc/systemd/system/hostapd.service.d
  cat >/etc/systemd/system/hostapd.service.d/minebox.conf <<'CONF'
[Unit]
After=systemd-networkd.service
Wants=systemd-networkd.service

[Service]
ExecStartPre=/usr/sbin/rfkill unblock wifi
ExecStartPost=/bin/sh -c '/sbin/iwconfig wlan0 power off 2>/dev/null || /usr/sbin/iw dev wlan0 set power_save off 2>/dev/null || true'
Restart=on-failure
RestartSec=3
CONF
fi

# Ensure rfkill unblock remains even when renderer wrote the drop-in.
mkdir -p /etc/systemd/system/hostapd.service.d
if ! grep -q 'rfkill unblock wifi' /etc/systemd/system/hostapd.service.d/minebox.conf 2>/dev/null; then
  cat >>/etc/systemd/system/hostapd.service.d/minebox.conf <<'CONF'

[Service]
ExecStartPre=/usr/sbin/rfkill unblock wifi
CONF
fi

# dnsmasq must start after SoftAP address is configured.
mkdir -p /etc/systemd/system/dnsmasq.service.d
cat >/etc/systemd/system/dnsmasq.service.d/minebox.conf <<'CONF'
[Unit]
After=systemd-networkd.service hostapd.service
Wants=systemd-networkd.service
CONF

# Load routing sysctls during image creation as well as on every real boot.
sysctl --system >/dev/null 2>&1 || true

systemctl daemon-reload
