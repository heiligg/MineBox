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
rm -rf "$ROOT_DIR/output"
mkdir -p "$ROOT_DIR/output"

if [ ! -d "$PI_GEN_DIR/.git" ]; then
  echo "Downloading the official 64-bit Raspberry Pi OS image builder..."
  git clone --depth 1 --branch arm64 https://github.com/RPi-Distro/pi-gen.git "$PI_GEN_DIR"
else
  echo "Updating pi-gen..."
  git -C "$PI_GEN_DIR" fetch --depth 1 origin arm64
  git -C "$PI_GEN_DIR" checkout -f arm64
  git -C "$PI_GEN_DIR" reset --hard origin/arm64
fi

# GitHub Actions already verifies ARM64 execution with an actual ARM64 Docker
# container before this script runs. pi-gen's host checks can reject that valid
# setup because its probe does not understand the setup-qemu-action registration.
# In CI only, bypass the redundant host probe and avoid reconfiguring binfmt from
# inside the privileged build container. Verify the exact upstream text first so
# future pi-gen changes fail clearly instead of being patched incorrectly.
if [ "${GITHUB_ACTIONS:-false}" = "true" ]; then
  docker_script="$PI_GEN_DIR/build-docker.sh"

  python3 - "$docker_script" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

replacements = {
    "    dpkg-reconfigure qemu-user-binfmt &&\n": "    true &&\n",
    "binfmt_misc_required=1\n": "binfmt_misc_required=0\n",
}

for old, new in replacements.items():
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"expected exactly one upstream pi-gen fragment, found {count}: {old.strip()}"
        )
    text = text.replace(old, new, 1)

path.write_text(text)
PY

  grep -Fqx '    true &&' "$docker_script" || {
    echo "ERROR: Failed to disable container qemu-user-binfmt reconfiguration."
    exit 1
  }
  grep -Fqx 'binfmt_misc_required=0' "$docker_script" || {
    echo "ERROR: Failed to disable the redundant pi-gen host ARM64 probe."
    exit 1
  }
  echo "Using GitHub Actions ARM64 binfmt registration."
fi

# pi-gen itself has a FILE named 'config'. Keep MineBox's configuration at
# the repository root under a different filename. Do not create pi-gen/config/.
install -m 0644 "$ROOT_DIR/config/minebox-pi5.conf" "$PI_GEN_CONFIG"

rm -rf "$PI_GEN_DIR/stage-minebox"
cp -a "$ROOT_DIR/pi-gen/stage-minebox" "$PI_GEN_DIR/stage-minebox"

# Every custom pi-gen stage must begin with the completed root filesystem from
# the previous stage. Without this hook, stage-minebox has no rootfs to chroot
# into and fails immediately when its package step starts.
cat > "$PI_GEN_DIR/stage-minebox/PRERUN.sh" <<'EOF'
#!/bin/bash -e

if [ ! -d "${ROOTFS_DIR}" ]; then
  copy_previous
fi
EOF
chmod 0755 "$PI_GEN_DIR/stage-minebox/PRERUN.sh"

# pi-gen only exports a disk image when the final stage contains this marker.
touch "$PI_GEN_DIR/stage-minebox/EXPORT_IMAGE"

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

mapfile -d '' image_files < <(
  find deploy -type f \
    \( -name '*.img' -o -name '*.img.xz' -o -name '*.img.gz' -o -name '*.zip' -o -name '*.bmap' \) \
    -print0
)

if [ "${#image_files[@]}" -eq 0 ]; then
  echo "ERROR: pi-gen completed without producing a deployable image."
  echo "Contents of pi-gen/deploy:"
  find deploy -maxdepth 3 -printf '%y %p %s bytes\n' 2>/dev/null || true
  echo "Recent pi-gen build log output:"
  find deploy -type f -name '*.log' -exec tail -n 100 {} \; 2>/dev/null || true
  exit 1
fi

for image_file in "${image_files[@]}"; do
  cp -v "$image_file" "$ROOT_DIR/output/"
done

echo
echo "Build complete. Output files are in:"
echo "  $ROOT_DIR/output"
find "$ROOT_DIR/output" -maxdepth 1 -type f -printf '%f %s bytes\n'
