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

for command in git rsync realpath python3; do
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
# container. pi-gen's host checks can reject that valid setup because its probe
# does not understand the setup-qemu-action registration. In CI only, bypass
# that redundant probe and avoid replacing the host binfmt registration.
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

# pi-gen itself has a FILE named 'config'. Keep MineBox's configuration at the
# repository root under a different filename.
install -m 0644 "$ROOT_DIR/config/minebox-pi5.conf" "$PI_GEN_CONFIG"

rm -rf "$PI_GEN_DIR/stage-minebox"
cp -a "$ROOT_DIR/pi-gen/stage-minebox" "$PI_GEN_DIR/stage-minebox"
CUSTOM_STAGE="$PI_GEN_DIR/stage-minebox"

# pi-gen recognizes the stage hook as lowercase prerun.sh. Ensure that exact
# file exists, contains the rootfs handoff, and is executable. Remove the
# incorrectly named uppercase variant so it cannot hide future mistakes.
rm -f "$CUSTOM_STAGE/PRERUN.sh"
cat > "$CUSTOM_STAGE/prerun.sh" <<'EOF'
#!/bin/bash -e

if [ ! -d "${ROOTFS_DIR}" ]; then
  copy_previous
fi
EOF
chmod 0755 "$CUSTOM_STAGE/prerun.sh"

# Normalize all pi-gen stage scripts because executable bits can be lost when
# files are copied, edited through APIs, or checked out on another platform.
while IFS= read -r -d '' script; do
  chmod 0755 "$script"
  bash -n "$script"
done < <(find "$CUSTOM_STAGE" -type f \( -name '*-run.sh' -o -name 'prerun.sh' \) -print0)

required_stage_files=(
  "$CUSTOM_STAGE/prerun.sh"
  "$CUSTOM_STAGE/00-install-minebox/00-packages"
  "$CUSTOM_STAGE/00-install-minebox/00-run.sh"
  "$CUSTOM_STAGE/00-install-minebox/00-run-chroot.sh"
  "$CUSTOM_STAGE/01-system-config/00-run.sh"
  "$CUSTOM_STAGE/01-system-config/00-run-chroot.sh"
)
for required_file in "${required_stage_files[@]}"; do
  [ -s "$required_file" ] || {
    echo "ERROR: Missing or empty custom-stage file: $required_file"
    exit 1
  }
done

grep -Fq 'copy_previous' "$CUSTOM_STAGE/prerun.sh" || {
  echo "ERROR: stage-minebox/prerun.sh does not inherit the previous rootfs."
  exit 1
}

# pi-gen only exports a disk image when the final stage contains this marker.
touch "$CUSTOM_STAGE/EXPORT_IMAGE"

# Refresh the embedded application each build so local UI changes enter the image.
rm -rf "$CUSTOM_STAGE/00-install-minebox/files/minebox"
mkdir -p "$CUSTOM_STAGE/00-install-minebox/files/minebox"
rsync -a --delete \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.backup' \
  --exclude='*.backup-*' \
  --exclude='*.bak' \
  "$ROOT_DIR/app/" \
  "$CUSTOM_STAGE/00-install-minebox/files/minebox/"
install -m 0644 "$ROOT_DIR/requirements.txt" \
  "$CUSTOM_STAGE/00-install-minebox/files/minebox/requirements.txt"

# Catch Python syntax errors after the exact application payload has been staged.
python3 -m compileall -q "$CUSTOM_STAGE/00-install-minebox/files/minebox"
find "$CUSTOM_STAGE/00-install-minebox/files/minebox" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$CUSTOM_STAGE/00-install-minebox/files/minebox" -type f -name '*.pyc' -delete

echo "Custom MineBox stage preflight passed."
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
