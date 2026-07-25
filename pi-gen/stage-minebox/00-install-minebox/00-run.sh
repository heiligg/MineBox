#!/bin/bash -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="${SCRIPT_DIR}/files/minebox"

# build.sh refreshes this directory from the repository-level app/ folder
# before invoking pi-gen. Stage scripts run inside pi-gen's copied stage tree,
# so the embedded files directory is the reliable source during local and CI builds.
if [ ! -d "$APP_DIR" ] || [ ! -f "$APP_DIR/main.py" ]; then
    echo "ERROR: MineBox application payload is missing from: $APP_DIR" >&2
    exit 1
fi

install -d "${ROOTFS_DIR}/opt/minebox"
echo "Installing MineBox from ${APP_DIR}"
cp -a "${APP_DIR}/." "${ROOTFS_DIR}/opt/minebox/"

install -d \
    "${ROOTFS_DIR}/opt/minecraft/server" \
    "${ROOTFS_DIR}/opt/minecraft/backups"
