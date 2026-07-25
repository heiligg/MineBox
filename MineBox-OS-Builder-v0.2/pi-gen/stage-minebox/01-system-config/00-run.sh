#!/bin/bash -e
install -m 0644 files/minebox-ui.service "${ROOTFS_DIR}/etc/systemd/system/minebox-ui.service"
install -m 0644 files/minebox-web.service "${ROOTFS_DIR}/etc/systemd/system/minebox-web.service"
install -m 0644 files/minecraft.service "${ROOTFS_DIR}/etc/systemd/system/minecraft.service"
install -m 0644 files/minebox-firstboot.service "${ROOTFS_DIR}/etc/systemd/system/minebox-firstboot.service"
install -m 0755 files/minebox-firstboot "${ROOTFS_DIR}/usr/local/sbin/minebox-firstboot"
