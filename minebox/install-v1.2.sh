#!/bin/bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="/opt/minebox"

if [ "${EUID}" -ne 0 ]; then
  echo "Run with: sudo bash install-v1.2.sh"
  exit 1
fi

mkdir -p "$TARGET_DIR"
cp -a "$SOURCE_DIR"/. "$TARGET_DIR"/
chown -R minebox:minebox "$TARGET_DIR"
chmod +x "$TARGET_DIR/scripts/maintenance_runner.py"

install -m 0644 "$TARGET_DIR/services/minebox-maintenance.service" /etc/systemd/system/minebox-maintenance.service
install -m 0644 "$TARGET_DIR/services/minebox-maintenance.timer" /etc/systemd/system/minebox-maintenance.timer
systemctl daemon-reload
systemctl enable --now minebox-maintenance.timer

echo "MineBox 1.2 installed in $TARGET_DIR"
echo "Maintenance timer enabled."
echo "Start the UI with: cd /opt/minebox && python3 main.py"
