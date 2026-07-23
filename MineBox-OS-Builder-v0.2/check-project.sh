#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

required=(
  "config/minebox-pi5.conf"
  "app/main.py"
  "app/menu.py"
  "pi-gen/stage-minebox/prerun.sh"
  "pi-gen/stage-minebox/EXPORT_IMAGE"
  "pi-gen/stage-minebox/00-install-minebox/00-packages"
  "pi-gen/stage-minebox/00-install-minebox/00-run.sh"
  "pi-gen/stage-minebox/00-install-minebox/00-run-chroot.sh"
  "pi-gen/stage-minebox/01-system-config/00-run.sh"
  "pi-gen/stage-minebox/01-system-config/00-run-chroot.sh"
  "pi-gen/stage-minebox/02-dedicated-hotspot/00-packages"
  "pi-gen/stage-minebox/02-dedicated-hotspot/01-run.sh"
  "pi-gen/stage-minebox/02-dedicated-hotspot/02-run-chroot.sh"
  "pi-gen/stage-minebox/02-dedicated-hotspot/files/hostapd.conf"
  "pi-gen/stage-minebox/02-dedicated-hotspot/files/dnsmasq-minebox.conf"
  "pi-gen/stage-minebox/02-dedicated-hotspot/files/20-minebox-wlan0.network"
  "pi-gen/stage-minebox/02-dedicated-hotspot/files/10-minebox-unmanaged.conf"
)

for item in "${required[@]}"; do
  [ -s "$ROOT_DIR/$item" ] || { echo "Missing or empty required file: $item"; exit 1; }
done

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

python3 -m compileall -q "$ROOT_DIR/app"
find "$ROOT_DIR/app" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT_DIR/app" -type f -name '*.pyc' -delete

echo "MineBox builder project check passed."
