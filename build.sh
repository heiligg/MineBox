#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${ROOT_DIR}/.build"
PI_GEN_DIR="${WORK_DIR}/pi-gen"
PI_GEN_CONFIG_NAME="minebox-pi5.conf"
PI_GEN_CONFIG="${PI_GEN_DIR}/${PI_GEN_CONFIG_NAME}"
MODE="${1:---docker}"

trap 'echo; echo "Build stopped on line ${LINENO}. Review the error above."' ERR

case "$MODE" in
  --docker|--native) ;;
  *) echo "Usage: ./build.sh [--docker|--native]"; exit 2 ;;
esac

for command in git rsync realpath; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Missing required command: $command"
    exit 1
  }
done

"${ROOT_DIR}/check-project.sh"
mkdir -p "$WORK_DIR"

if [ ! -d "$PI_GEN_DIR/.git" ]; then
  echo "Downloading the official 64-bit Raspberry Pi OS image builder..."
  git clone --depth 1 --branch arm64 https://github.com/RPi-Distro/pi-gen.git "$PI_GEN_DIR"
else
  echo "Updating pi-gen..."
  git -C "$PI_GEN_DIR" fetch --depth 1 origin arm64
  git -C "$PI_GEN_DIR" checkout -f arm64
  git -C "$PI_GEN_DIR" reset --hard origin/arm64
fi

# pi-gen itself has a FILE named 'config'. Keep MineBox's configuration at
# the repository root under a different filename. Do not create pi-gen/config/.
install -m 0644 "$ROOT_DIR/config/minebox-pi5.conf" "$PI_GEN_CONFIG"

rm -rf "$PI_GEN_DIR/stage-minebox"
cp -a "$ROOT_DIR/pi-gen/stage-minebox" "$PI_GEN_DIR/stage-minebox"

# Refresh the embedded application each build so local UI changes enter the image.
rm -rf "$PI_GEN_DIR/stage-minebox/00-install-minebox/files/minebox"
mkdir -p "$PI_GEN_DIR/stage-minebox/00-install-minebox/files/minebox"
rsync -a --delete \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  "$ROOT_DIR/app/" \
  "$PI_GEN_DIR/stage-minebox/00-install-minebox/files/minebox/"

cd "$PI_GEN_DIR"

if [ "$MODE" = "--docker" ]; then
  command -v docker >/dev/null 2>&1 || {
    echo "Docker is not installed. Install Docker or run ./build.sh --native"
    exit 1
  }
  docker info >/dev/null 2>&1 || {
    echo "Docker is installed, but your user cannot access it."
    echo "Log out and back in after: sudo usermod -aG docker \"$USER\""
    exit 1
  }
  PRESERVE_CONTAINER=1 ./build-docker.sh -c "$PI_GEN_CONFIG_NAME"
else
  sudo ./build.sh -c "$PI_GEN_CONFIG_NAME"
fi

mkdir -p "$ROOT_DIR/output"
find deploy -maxdepth 1 -type f \
  \( -name '*.img' -o -name '*.img.xz' -o -name '*.img.gz' -o -name '*.zip' -o -name '*.bmap' \) \
  -exec cp -v {} "$ROOT_DIR/output/" \;

echo
echo "Build complete. Output files are in:"
echo "  $ROOT_DIR/output"
