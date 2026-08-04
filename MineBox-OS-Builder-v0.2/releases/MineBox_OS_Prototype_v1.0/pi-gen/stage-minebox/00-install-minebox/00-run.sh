#!/bin/bash -e

install -d "${ROOTFS_DIR}/opt/minebox"
# build.sh rsyncs app/ into files/minebox/ before pi-gen runs.
cp -a files/minebox/. "${ROOTFS_DIR}/opt/minebox/"
find "${ROOTFS_DIR}/opt/minebox" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "${ROOTFS_DIR}/opt/minebox" -type f \( -name '*.pyc' -o -name '*.backup' -o -name '*.backup-*' -o -name '*.bak' \) -delete

install -d \
    "${ROOTFS_DIR}/opt/minecraft/server" \
    "${ROOTFS_DIR}/opt/minecraft/servers" \
    "${ROOTFS_DIR}/opt/minecraft/metadata" \
    "${ROOTFS_DIR}/opt/minecraft/backups"
