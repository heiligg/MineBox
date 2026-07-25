#!/bin/bash -e

getent group minebox >/dev/null || groupadd --system minebox
id minecraft >/dev/null 2>&1 || useradd --system --home /opt/minecraft --shell /usr/sbin/nologin --gid minebox minecraft
usermod -aG minebox minebox

# hostnamectl requires a running systemd instance, which does not exist while
# pi-gen is configuring the image in a chroot. Configure the hostname directly.
printf '%s\n' 'minebox' >/etc/hostname
if grep -qE '^127\.0\.1\.1[[:space:]]' /etc/hosts; then
    sed -i -E 's/^127\.0\.1\.1[[:space:]].*/127.0.1.1\tminebox/' /etc/hosts
else
    printf '%s\n' '127.0.1.1\tminebox' >>/etc/hosts
fi

install -m 0755 /opt/minebox/scripts/set_hostname.py /usr/local/sbin/minebox-set-hostname
mkdir -p /etc/avahi/services
install -m 0644 /opt/minebox/services/avahi/minebox.service /etc/avahi/services/minebox.service

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
minebox ALL=(root) NOPASSWD: /usr/bin/systemctl start minecraft.service, /usr/bin/systemctl stop minecraft.service, /usr/bin/systemctl restart minecraft.service, /usr/bin/systemctl poweroff, /usr/bin/systemctl reboot, /usr/local/sbin/minebox-set-hostname *
SUDOERS
chmod 0440 /etc/sudoers.d/minebox
visudo -cf /etc/sudoers.d/minebox

mkdir -p /var/lib/minebox /var/log/minebox
chown -R minebox:minebox /var/lib/minebox /var/log/minebox

# "systemctl enable" only creates boot-time symlinks and is safe in a chroot;
# do not use commands such as start, restart, or hostnamectl during image build.
systemctl enable minebox-maintenance.timer
systemctl enable minebox-network.service
systemctl enable avahi-daemon.service
