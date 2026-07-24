#!/bin/bash -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SEARCH_DIR="$SCRIPT_DIR"
APP_DIR=""

# The stage exists under either pi-gen/ or .build/pi-gen/. Walk upward so
# both layouts install the same repository-level app/ source tree.
while [ "$SEARCH_DIR" != "/" ]; do
    if [ -d "$SEARCH_DIR/app" ] && [ -f "$SEARCH_DIR/app/main.py" ]; then
        APP_DIR="$SEARCH_DIR/app"
        break
    fi
    SEARCH_DIR="$(dirname "$SEARCH_DIR")"
done

if [ -z "$APP_DIR" ]; then
    echo "ERROR: Could not locate the MineBox app/ source directory." >&2
    exit 1
fi

install -d "${ROOTFS_DIR}/opt/minebox"
echo "Installing MineBox from ${APP_DIR}"
cp -a "${APP_DIR}/." "${ROOTFS_DIR}/opt/minebox/"

install -d     "${ROOTFS_DIR}/opt/minecraft/server"     "${ROOTFS_DIR}/opt/minecraft/backups"
