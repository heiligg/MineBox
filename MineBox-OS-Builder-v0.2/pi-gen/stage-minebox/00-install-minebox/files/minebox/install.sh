#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="/opt/minebox"
MINECRAFT_DIR="/opt/minecraft/server"
BACKUP_DIR="/opt/minecraft/backups"
MINEBOX_USER="minebox"
MINECRAFT_USER="minecraft"
SHARED_GROUP="minebox"
SUDOERS_FILE="/etc/sudoers.d/minebox"

if [ "${EUID}" -ne 0 ]; then
  echo "Run this installer once with: sudo bash install.sh"
  exit 1
fi

for user in "$MINEBOX_USER" "$MINECRAFT_USER"; do
  if ! id "$user" >/dev/null 2>&1; then
    echo "Required user '$user' does not exist."
    exit 1
  fi
done

getent group "$SHARED_GROUP" >/dev/null 2>&1 || groupadd "$SHARED_GROUP"
usermod -aG "$SHARED_GROUP" "$MINEBOX_USER"
usermod -aG "$SHARED_GROUP" "$MINECRAFT_USER"

mkdir -p "$TARGET_DIR" "$MINECRAFT_DIR" "$BACKUP_DIR"
cp -a "$SOURCE_DIR"/. "$TARGET_DIR"/
rm -rf "$TARGET_DIR"/__pycache__ "$TARGET_DIR"/services/__pycache__ "$TARGET_DIR"/scripts/__pycache__
chown -R "$MINEBOX_USER:$SHARED_GROUP" "$TARGET_DIR"
chmod -R u=rwX,g=rX,o=rX "$TARGET_DIR"
chmod +x "$TARGET_DIR/install.sh" "$TARGET_DIR/scripts/maintenance_runner.py"

# MineBox and Minecraft share access to server data. The setgid bit keeps all
# new folders in the shared group, and group write access prevents runtime
# password prompts for backups, settings, logs, worlds, and server.properties.
chown -R "$MINECRAFT_USER:$SHARED_GROUP" /opt/minecraft
find /opt/minecraft -type d -exec chmod 2775 {} +
find /opt/minecraft -type f -exec chmod 0664 {} +

# Default ACLs keep future files writable even when programs choose a strict umask.
if command -v setfacl >/dev/null 2>&1; then
  setfacl -R -m "u:${MINEBOX_USER}:rwX,u:${MINECRAFT_USER}:rwX,g:${SHARED_GROUP}:rwX" /opt/minecraft
  setfacl -R -d -m "u:${MINEBOX_USER}:rwX,u:${MINECRAFT_USER}:rwX,g:${SHARED_GROUP}:rwX,m::rwX" /opt/minecraft
fi

# Make files created by minecraft.service group-writable in the future.
mkdir -p /etc/systemd/system/minecraft.service.d
cat > /etc/systemd/system/minecraft.service.d/minebox-permissions.conf <<'OVERRIDE'
[Service]
UMask=0002
OVERRIDE

# Runtime actions are passwordless for Minecraft control, updates, TLS, and helpers.
cat > "$SUDOERS_FILE" <<'SUDOERS'
minebox ALL=(root) NOPASSWD: /usr/bin/systemctl start minecraft.service, /usr/bin/systemctl stop minecraft.service, /usr/bin/systemctl restart minecraft.service, /usr/bin/systemctl start minebox-update.service, /usr/bin/systemctl stop hostapd.service, /usr/bin/systemctl start hostapd.service, /usr/bin/systemctl stop dnsmasq.service, /usr/bin/systemctl start dnsmasq.service, /usr/bin/systemctl enable avahi-daemon.service, /usr/bin/systemctl start avahi-daemon.service, /usr/bin/systemctl try-reload-or-restart avahi-daemon.service, /usr/bin/python3 /opt/minebox/scripts/minebox_fix_minecraft_perms.py, /usr/local/sbin/minebox-fix-minecraft-perms, /usr/bin/python3 /opt/minebox/scripts/minebox_install_avahi.py, /usr/local/sbin/minebox-install-avahi, /usr/bin/python3 /opt/minebox/scripts/minebox_ensure_java.py, /usr/local/sbin/minebox-ensure-java, /usr/bin/python3 /opt/minebox/scripts/minebox_ensure_tls.py, /usr/bin/python3 /opt/minebox/scripts/minebox_ensure_tls.py *, /usr/local/sbin/minebox-ensure-tls, /usr/local/sbin/minebox-ensure-tls *, /usr/bin/systemctl restart minebox-api.service, /usr/bin/python3 /opt/minebox/scripts/minebox_fan_test.py *, /usr/local/sbin/minebox-fan-test *, /usr/bin/journalctl -u minecraft.service *, /usr/bin/systemctl poweroff, /usr/bin/systemctl reboot, /usr/bin/python3 /opt/minebox/scripts/minebox_set_os_password.py minebox
SUDOERS
chmod 0440 "$SUDOERS_FILE"
visudo -cf "$SUDOERS_FILE"

if [ -f "$TARGET_DIR/scripts/minebox_ensure_tls.py" ]; then
  install -m 0755 "$TARGET_DIR/scripts/minebox_ensure_tls.py" /usr/local/sbin/minebox-ensure-tls
fi
if [ -f "$TARGET_DIR/scripts/minebox_api_run.py" ]; then
  chmod 0755 "$TARGET_DIR/scripts/minebox_api_run.py"
fi

install -m 0644 "$TARGET_DIR/services/minebox.service" /etc/systemd/system/minebox.service
install -m 0644 "$TARGET_DIR/services/minebox-maintenance.service" /etc/systemd/system/minebox-maintenance.service
install -m 0644 "$TARGET_DIR/services/minebox-maintenance.timer" /etc/systemd/system/minebox-maintenance.timer

systemctl daemon-reload
systemctl enable minebox.service >/dev/null 2>&1 || true
systemctl enable --now minebox-maintenance.timer

# Refresh current server files after applying the service umask override.
if systemctl is-active --quiet minecraft.service; then
  systemctl restart minecraft.service
fi

echo
echo "MineBox 1.3.1 installed successfully."
echo "Runtime features will not ask for a sudo password."
echo "Log out and back in once so the minebox group membership refreshes."
echo "Then launch with: cd /opt/minebox && python3 main.py"
