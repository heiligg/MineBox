#!/bin/bash -e

getent group minebox >/dev/null || groupadd --system minebox
id minecraft >/dev/null 2>&1 || useradd --system --home /opt/minecraft --shell /usr/sbin/nologin --gid minebox minecraft
usermod -aG minebox minebox

chown -R minebox:minebox /opt/minebox
chmod -R u=rwX,g=rX,o= /opt/minebox
find /opt/minebox -type f -name '*.sh' -exec chmod +x {} +
find /opt/minebox/scripts -type f -name '*.py' -exec chmod +x {} + 2>/dev/null || true

install -d /opt/minecraft/servers /opt/minecraft/metadata /opt/minecraft/backups
chown -R minebox:minebox /opt/minecraft
chmod -R 2770 /opt/minecraft/servers /opt/minecraft/metadata /opt/minecraft/backups
# Legacy single-server path kept for migration compatibility.
install -d /opt/minecraft/server
chown -R minecraft:minebox /opt/minecraft/server
chmod -R 2770 /opt/minecraft/server

setfacl -R -m u:minebox:rwX,u:minecraft:rwX,g:minebox:rwX,m::rwX /opt/minecraft
setfacl -R -d -m u:minebox:rwX,u:minecraft:rwX,g:minebox:rwX,m::rwX /opt/minecraft

if [ -f /opt/minebox/requirements.txt ]; then
    pip3 install --break-system-packages -r /opt/minebox/requirements.txt
fi

install -m 0644 /opt/minebox/services/minebox-api.service /etc/systemd/system/minebox-api.service
install -m 0644 /opt/minebox/services/minebox-update.service /etc/systemd/system/minebox-update.service
install -m 0644 /opt/minebox/services/minebox-maintenance.service /etc/systemd/system/minebox-maintenance.service
install -m 0644 /opt/minebox/services/minebox-maintenance.timer /etc/systemd/system/minebox-maintenance.timer

# Do not install the old NetworkManager hotspot guard. The dedicated hotspot
# stage configures hostapd and dnsmasq as the sole owners of wlan0.
rm -f /etc/systemd/system/minebox-network.service

install -d /etc/minebox
cat >/etc/minebox/updates.conf <<'CONF'
# MineBox GitHub update configuration
repo=https://github.com/heiligg/MineBox.git
branch=main
app_subdir=MineBox-OS-Builder-v0.2/app
CONF
chmod 0644 /etc/minebox/updates.conf

cat >/etc/sudoers.d/minebox <<'SUDOERS'
minebox ALL=(root) NOPASSWD: /usr/bin/systemctl start minecraft.service, /usr/bin/systemctl stop minecraft.service, /usr/bin/systemctl restart minecraft.service, /usr/bin/systemctl start minebox-update.service, /usr/bin/systemctl stop hostapd.service, /usr/bin/systemctl start hostapd.service, /usr/bin/systemctl stop dnsmasq.service, /usr/bin/systemctl start dnsmasq.service, /usr/bin/python3 /opt/minebox/scripts/minebox_fix_minecraft_perms.py, /usr/local/sbin/minebox-fix-minecraft-perms, /usr/bin/systemctl poweroff, /usr/bin/systemctl reboot
SUDOERS
chmod 0440 /etc/sudoers.d/minebox
visudo -cf /etc/sudoers.d/minebox

mkdir -p /var/lib/minebox /var/lib/minebox/updates /var/log/minebox
chown -R minebox:minebox /var/lib/minebox /var/log/minebox

systemctl enable minebox-api.service
systemctl enable minebox-maintenance.timer
