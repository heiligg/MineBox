#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="/opt/minebox"
MINECRAFT_DIR="/opt/minecraft/server"
BACKUP_DIR="/opt/minecraft/backups"
MINEBOX_USER="minebox"
MINECRAFT_USER="minecraft"
SHARED_GROUP="minebox"
DEFAULT_HOSTNAME="${MINEBOX_HOSTNAME:-minebox}"
SUDOERS_FILE="/etc/sudoers.d/minebox"

if [ "${EUID}" -ne 0 ]; then
  echo "Run this installer once with: sudo bash install.sh"
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y avahi-daemon libnss-mdns

hostnamectl set-hostname "$DEFAULT_HOSTNAME"

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
chmod +x "$TARGET_DIR/install.sh" "$TARGET_DIR/scripts/maintenance_runner.py" "$TARGET_DIR/scripts/set_hostname.py"

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

# Runtime actions are passwordless, but only for these exact service/power commands.
cat > "$SUDOERS_FILE" <<'SUDOERS'
minebox ALL=(root) NOPASSWD: /usr/bin/systemctl start minecraft.service, /usr/bin/systemctl stop minecraft.service, /usr/bin/systemctl restart minecraft.service, /usr/bin/systemctl poweroff, /usr/bin/systemctl reboot, /usr/local/sbin/minebox-set-hostname *
SUDOERS
install -m 0755 "$TARGET_DIR/scripts/set_hostname.py" /usr/local/sbin/minebox-set-hostname
mkdir -p /etc/avahi/services
install -m 0644 "$TARGET_DIR/services/avahi/minebox.service" /etc/avahi/services/minebox.service
systemctl enable --now avahi-daemon.service

chmod 0440 "$SUDOERS_FILE"
visudo -cf "$SUDOERS_FILE"

# Allow the MineBox service account to manage NetworkManager connections
# through the dashboard without granting unrestricted root access.
mkdir -p /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/50-minebox-network.rules <<'POLKIT'
polkit.addRule(function(action, subject) {
    if (subject.isInGroup("minebox") && (
        action.id === "org.freedesktop.NetworkManager.network-control" ||
        action.id === "org.freedesktop.NetworkManager.settings.modify.system" ||
        action.id === "org.freedesktop.NetworkManager.enable-disable-wifi"
    )) {
        return polkit.Result.YES;
    }
});
POLKIT
chmod 0644 /etc/polkit-1/rules.d/50-minebox-network.rules

# NetworkManager's IPv4 shared mode creates DHCP, DNS, NAT, and firewall
# rules. Keep kernel forwarding enabled as a durable appliance default.
cat > /etc/sysctl.d/90-minebox-internet-sharing.conf <<'SYSCTL'
net.ipv4.ip_forward=1
SYSCTL
sysctl --system >/dev/null

install -m 0644 "$TARGET_DIR/services/minebox.service" /etc/systemd/system/minebox.service
install -m 0644 "$TARGET_DIR/services/minebox-maintenance.service" /etc/systemd/system/minebox-maintenance.service
install -m 0644 "$TARGET_DIR/services/minebox-maintenance.timer" /etc/systemd/system/minebox-maintenance.timer
install -m 0644 "$TARGET_DIR/services/minebox-network.service" /etc/systemd/system/minebox-network.service

systemctl daemon-reload
systemctl enable minebox.service >/dev/null 2>&1 || true
systemctl enable --now minebox-maintenance.timer
systemctl enable --now minebox-network.service

# Refresh current server files after applying the service umask override.
if systemctl is-active --quiet minecraft.service; then
  systemctl restart minecraft.service
fi

echo
echo "MineBox 1.3.1 installed successfully."
echo "Runtime features will not ask for a sudo password."
echo "The automatic setup hotspot service is enabled."
echo "Dashboard: http://${DEFAULT_HOSTNAME}.local:8080"
echo "Minecraft: ${DEFAULT_HOSTNAME}.local"
echo "Log out and back in once so the minebox group membership refreshes."
echo "Then launch with: cd /opt/minebox && python3 main.py"
