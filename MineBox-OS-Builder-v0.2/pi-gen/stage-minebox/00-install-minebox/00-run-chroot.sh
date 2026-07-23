#!/bin/bash -e

getent group minebox >/dev/null || groupadd --system minebox
id minecraft >/dev/null 2>&1 || useradd --system --home /opt/minecraft --shell /usr/sbin/nologin --gid minebox minecraft
usermod -aG minebox minebox

chown -R minebox:minebox /opt/minebox
chmod -R u=rwX,g=rX,o= /opt/minebox
find /opt/minebox -type f -name '*.sh' -exec chmod +x {} +
find /opt/minebox/scripts -type f -name '*.py' -exec chmod +x {} + 2>/dev/null || true

chown -R minecraft:minebox /opt/minecraft/server
chmod -R 2770 /opt/minecraft/server
chown -R minebox:minebox /opt/minecraft/backups
chmod -R 2770 /opt/minecraft/backups

setfacl -R -m u:minebox:rwX,u:minecraft:rwX,g:minebox:rwX,m::rwX /opt/minecraft
setfacl -R -d -m u:minebox:rwX,u:minecraft:rwX,g:minebox:rwX,m::rwX /opt/minecraft

install -m 0644 /opt/minebox/services/minebox-maintenance.service /etc/systemd/system/minebox-maintenance.service
install -m 0644 /opt/minebox/services/minebox-maintenance.timer /etc/systemd/system/minebox-maintenance.timer
install -m 0644 /opt/minebox/services/minebox-network.service /etc/systemd/system/minebox-network.service

cat >/etc/sudoers.d/minebox <<'SUDOERS'
minebox ALL=(root) NOPASSWD: /usr/bin/systemctl start minecraft.service, /usr/bin/systemctl stop minecraft.service, /usr/bin/systemctl restart minecraft.service, /usr/bin/systemctl poweroff, /usr/bin/systemctl reboot
SUDOERS
chmod 0440 /etc/sudoers.d/minebox
visudo -cf /etc/sudoers.d/minebox

mkdir -p /var/lib/minebox /var/log/minebox
chown -R minebox:minebox /var/lib/minebox /var/log/minebox

systemctl enable minebox-maintenance.timer
systemctl enable minebox-network.service
