#!/bin/bash -e

install -m 0644 files/hostapd.conf "${ROOTFS_DIR}/etc/hostapd/hostapd.conf"
install -m 0644 files/dnsmasq-minebox.conf "${ROOTFS_DIR}/etc/dnsmasq.d/minebox.conf"
install -m 0644 files/20-minebox-wlan0.network "${ROOTFS_DIR}/etc/systemd/network/20-minebox-wlan0.network"
install -m 0644 files/10-minebox-unmanaged.conf "${ROOTFS_DIR}/etc/NetworkManager/conf.d/10-minebox-unmanaged.conf"
