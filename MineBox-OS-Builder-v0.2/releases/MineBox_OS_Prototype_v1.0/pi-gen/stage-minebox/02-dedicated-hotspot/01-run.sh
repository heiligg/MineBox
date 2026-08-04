#!/bin/bash -e

install -m 0644 files/hostapd.conf "${ROOTFS_DIR}/etc/hostapd/hostapd.conf"
install -m 0644 files/dnsmasq-minebox.conf "${ROOTFS_DIR}/etc/dnsmasq.d/minebox.conf"
install -m 0644 files/20-minebox-wlan0.network "${ROOTFS_DIR}/etc/systemd/network/20-minebox-wlan0.network"
install -m 0644 files/10-minebox-unmanaged.conf "${ROOTFS_DIR}/etc/NetworkManager/conf.d/10-minebox-unmanaged.conf"
install -m 0644 files/minebox-hotspot.nft "${ROOTFS_DIR}/etc/nftables.conf"
install -m 0644 files/90-minebox-router.conf "${ROOTFS_DIR}/etc/sysctl.d/90-minebox-router.conf"

# Captive portal unit is installed from /opt/minebox during the MineBox app stage;
# enable it here once the package tree is present.
if [ -f "${ROOTFS_DIR}/opt/minebox/services/minebox-captive.service" ]; then
  install -m 0644 \
    "${ROOTFS_DIR}/opt/minebox/services/minebox-captive.service" \
    "${ROOTFS_DIR}/etc/systemd/system/minebox-captive.service"
fi
