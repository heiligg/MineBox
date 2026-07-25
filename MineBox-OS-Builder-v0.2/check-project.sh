#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

required_nonempty=(
  "config/minebox-pi5.conf"
  "app/main.py"
  "app/menu.py"
  "app/api/server.py"
  "app/api/routes/dashboard.py"
  "app/web/templates/index.html"
  "pi-gen/stage-minebox/prerun.sh"
  "pi-gen/stage-minebox/00-install-minebox/00-packages"
  "pi-gen/stage-minebox/00-install-minebox/00-run.sh"
  "pi-gen/stage-minebox/00-install-minebox/00-run-chroot.sh"
  "pi-gen/stage-minebox/01-system-config/00-run.sh"
  "pi-gen/stage-minebox/01-system-config/00-run-chroot.sh"
  "pi-gen/stage-minebox/01-system-config/files/minebox-ui.service"
  "pi-gen/stage-minebox/01-system-config/files/minebox-web.service"
  "pi-gen/stage-minebox/01-system-config/files/minebox-firstboot.service"
  "pi-gen/stage-minebox/02-dedicated-hotspot/00-packages"
  "pi-gen/stage-minebox/02-dedicated-hotspot/01-run.sh"
  "pi-gen/stage-minebox/02-dedicated-hotspot/02-run-chroot.sh"
  "pi-gen/stage-minebox/02-dedicated-hotspot/files/hostapd.conf"
  "pi-gen/stage-minebox/02-dedicated-hotspot/files/dnsmasq-minebox.conf"
  "pi-gen/stage-minebox/02-dedicated-hotspot/files/20-minebox-wlan0.network"
  "pi-gen/stage-minebox/02-dedicated-hotspot/files/10-minebox-unmanaged.conf"
  "pi-gen/stage-minebox/02-dedicated-hotspot/files/minebox-hotspot.nft"
  "pi-gen/stage-minebox/02-dedicated-hotspot/files/90-minebox-router.conf"
)

for item in "${required_nonempty[@]}"; do
  [ -s "$ROOT_DIR/$item" ] || { echo "Missing or empty required file: $item"; exit 1; }
done

# EXPORT_IMAGE is intentionally an empty pi-gen marker. It only needs to exist.
[ -e "$ROOT_DIR/pi-gen/stage-minebox/EXPORT_IMAGE" ] || {
  echo "Missing required pi-gen marker: pi-gen/stage-minebox/EXPORT_IMAGE"
  exit 1
}

if [ -e "$ROOT_DIR/pi-gen/config" ]; then
  echo "Invalid layout: pi-gen/config must not exist. pi-gen reserves 'config' as a file."
  exit 1
fi

while IFS= read -r -d '' script; do
  bash -n "$script"
done < <(find "$ROOT_DIR" -path "$ROOT_DIR/.build" -prune -o -type f -name '*.sh' -print0)

# Fail early if hotspot settings drift away from the compatibility profile.
grep -Fqx 'ssid=MineBox-Setup' "$ROOT_DIR/pi-gen/stage-minebox/02-dedicated-hotspot/files/hostapd.conf"
grep -Fqx 'hw_mode=g' "$ROOT_DIR/pi-gen/stage-minebox/02-dedicated-hotspot/files/hostapd.conf"
grep -Fqx 'channel=6' "$ROOT_DIR/pi-gen/stage-minebox/02-dedicated-hotspot/files/hostapd.conf"
grep -Fqx 'wpa=2' "$ROOT_DIR/pi-gen/stage-minebox/02-dedicated-hotspot/files/hostapd.conf"
grep -Fqx 'rsn_pairwise=CCMP' "$ROOT_DIR/pi-gen/stage-minebox/02-dedicated-hotspot/files/hostapd.conf"
grep -Fq '192.168.4.1/24' "$ROOT_DIR/pi-gen/stage-minebox/02-dedicated-hotspot/files/20-minebox-wlan0.network"
grep -Fqx 'unmanaged-devices=interface-name:wlan0' "$ROOT_DIR/pi-gen/stage-minebox/02-dedicated-hotspot/files/10-minebox-unmanaged.conf"
grep -Fqx 'bind-dynamic' "$ROOT_DIR/pi-gen/stage-minebox/02-dedicated-hotspot/files/dnsmasq-minebox.conf"
! grep -Fqx 'no-resolv' "$ROOT_DIR/pi-gen/stage-minebox/02-dedicated-hotspot/files/dnsmasq-minebox.conf"
grep -Fqx 'net.ipv4.ip_forward=1' "$ROOT_DIR/pi-gen/stage-minebox/02-dedicated-hotspot/files/90-minebox-router.conf"
grep -Fq 'masquerade' "$ROOT_DIR/pi-gen/stage-minebox/02-dedicated-hotspot/files/minebox-hotspot.nft"
grep -Fq 'systemctl enable nftables.service' "$ROOT_DIR/pi-gen/stage-minebox/02-dedicated-hotspot/02-run-chroot.sh"

# Local and browser dashboards must start without waiting on upstream internet.
! grep -Fq 'network-online.target' "$ROOT_DIR/pi-gen/stage-minebox/01-system-config/files/minebox-ui.service"
! grep -Fq 'network-online.target' "$ROOT_DIR/pi-gen/stage-minebox/01-system-config/files/minebox-web.service"
! grep -Fq 'network-online.target' "$ROOT_DIR/pi-gen/stage-minebox/01-system-config/files/minebox-firstboot.service"
grep -Fqx 'ExecStart=/usr/bin/python3 /opt/minebox/main.py' "$ROOT_DIR/pi-gen/stage-minebox/01-system-config/files/minebox-ui.service"
grep -Fqx 'ExecStart=/usr/bin/python3 -m uvicorn api.server:app --host 0.0.0.0 --port 80' "$ROOT_DIR/pi-gen/stage-minebox/01-system-config/files/minebox-web.service"
grep -Fq 'systemctl enable minebox-web.service' "$ROOT_DIR/pi-gen/stage-minebox/01-system-config/00-run-chroot.sh"
grep -Fqx 'python3-fastapi' "$ROOT_DIR/pi-gen/stage-minebox/00-install-minebox/00-packages"
grep -Fqx 'python3-uvicorn' "$ROOT_DIR/pi-gen/stage-minebox/00-install-minebox/00-packages"

python3 -m compileall -q "$ROOT_DIR/app"
find "$ROOT_DIR/app" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT_DIR/app" -type f -name '*.pyc' -delete

echo "MineBox builder project check passed."
