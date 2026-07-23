#!/bin/bash -e
install -d "${ROOTFS_DIR}/opt/minebox"
cp -a files/minebox/. "${ROOTFS_DIR}/opt/minebox/"
install -d "${ROOTFS_DIR}/opt/minecraft/server" "${ROOTFS_DIR}/opt/minecraft/backups"
