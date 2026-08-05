#!/bin/bash -e

getent group minebox >/dev/null || groupadd --system minebox
id minecraft >/dev/null 2>&1 || useradd --system --home /opt/minecraft --shell /usr/sbin/nologin --gid minebox minecraft
# FIRST_USER_NAME=minebox from pi-gen config; ensure group membership.
id minebox >/dev/null 2>&1 && usermod -aG minebox minebox || true
for grp in video input render gpio systemd-journal; do
  getent group "$grp" >/dev/null 2>&1 && usermod -aG "$grp" minebox || true
done

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
    # Soft-fail: image build must not die on an optional pip package.
    pip3 install --break-system-packages -r /opt/minebox/requirements.txt \
      || pip3 install -r /opt/minebox/requirements.txt \
      || echo "WARNING: pip requirements install had errors (continuing)"
fi

install -m 0644 /opt/minebox/services/minebox-api.service /etc/systemd/system/minebox-api.service
install -m 0644 /opt/minebox/services/minebox-update.service /etc/systemd/system/minebox-update.service
install -m 0644 /opt/minebox/services/minebox-maintenance.service /etc/systemd/system/minebox-maintenance.service
install -m 0644 /opt/minebox/services/minebox-maintenance.timer /etc/systemd/system/minebox-maintenance.timer
install -m 0644 /opt/minebox/services/minebox-captive.service /etc/systemd/system/minebox-captive.service
if [ -f /opt/minebox/services/minebox-display.service ]; then
  install -m 0644 /opt/minebox/services/minebox-display.service /etc/systemd/system/minebox-display.service
fi

# Do not install the old NetworkManager hotspot guard. The dedicated hotspot
# stage configures hostapd and dnsmasq as the sole owners of the SoftAP iface.
rm -f /etc/systemd/system/minebox-network.service

install -d /etc/minebox
cat >/etc/minebox/updates.conf <<'CONF'
# MineBox GitHub update configuration
repo=https://github.com/heiligg/MineBox.git
branch=main
app_subdir=MineBox-OS-Builder-v0.2/app
CONF
chmod 0644 /etc/minebox/updates.conf

# Canonical sudoers (includes minebox_set_os_password.py, render helper, nft, hostapd restart).
if [ -f /opt/minebox/services/sudoers/minebox ]; then
  install -m 0440 /opt/minebox/services/sudoers/minebox /etc/sudoers.d/minebox
else
  echo "ERROR: missing /opt/minebox/services/sudoers/minebox" >&2
  exit 1
fi
visudo -cf /etc/sudoers.d/minebox

if [ -f /opt/minebox/scripts/minebox_ensure_tls.py ]; then
  install -m 0755 /opt/minebox/scripts/minebox_ensure_tls.py /usr/local/sbin/minebox-ensure-tls
fi
if [ -f /opt/minebox/scripts/minebox_api_run.py ]; then
  chmod 0755 /opt/minebox/scripts/minebox_api_run.py
fi

# Allow minebox-api to scan/join Wi-Fi via NetworkManager without a desktop session.
if [ -f /opt/minebox/services/polkit/10-minebox-networkmanager.rules ]; then
  install -d /etc/polkit-1/rules.d
  install -m 0644 /opt/minebox/services/polkit/10-minebox-networkmanager.rules \
    /etc/polkit-1/rules.d/10-minebox-networkmanager.rules
fi

mkdir -p /var/lib/minebox /var/lib/minebox/updates /var/log/minebox
chown -R minebox:minebox /var/lib/minebox /var/log/minebox

# Seed example config when absent (first-boot wizard / API will refine).
if [ ! -f /etc/minebox/minebox.toml ]; then
  for cand in \
    /opt/minebox/config/minebox.example.toml \
    /opt/minebox/../config/minebox.example.toml; do
    if [ -f "$cand" ]; then
      install -m 0644 "$cand" /etc/minebox/minebox.toml
      break
    fi
  done
fi
if [ ! -f /etc/minebox/hardware.toml ]; then
  for cand in \
    /opt/minebox/config/hardware.example.toml \
    /opt/minebox/../config/hardware.example.toml; do
    if [ -f "$cand" ]; then
      install -m 0644 "$cand" /etc/minebox/hardware.toml
      break
    fi
  done
fi

# Plymouth theme (best-effort during image build).
if [ -d /opt/minebox/boot/minebox-plymouth-theme ] && command -v plymouth-set-default-theme >/dev/null 2>&1; then
  mkdir -p /usr/share/plymouth/themes/minebox
  cp -a /opt/minebox/boot/minebox-plymouth-theme/. /usr/share/plymouth/themes/minebox/ || true
  plymouth-set-default-theme minebox || true
fi

systemctl enable minebox-api.service
systemctl enable minebox-maintenance.timer
systemctl enable minebox-captive.service >/dev/null 2>&1 || true

# Enable Chromium kiosk when packages are present in the image.
if command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1; then
  if command -v xinit >/dev/null 2>&1 && [ -f /etc/systemd/system/minebox-display.service ]; then
    systemctl enable minebox-display.service
  fi
fi
