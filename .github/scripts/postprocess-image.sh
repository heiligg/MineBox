#!/usr/bin/env bash
# Post-process pi-gen output: ensure .img.xz + SHA256 + collect logs.
set -euo pipefail

BUILDER_DIR="${1:-MineBox-OS-Builder-v0.2}"
OUT_DIR="${BUILDER_DIR}/output"
ART_DIR="${BUILDER_DIR}/ci-artifacts"
LOG_DIR="${ART_DIR}/logs"
mkdir -p "$OUT_DIR" "$ART_DIR" "$LOG_DIR"

echo "==> Collecting pi-gen / Docker logs"
if [[ -d "${BUILDER_DIR}/.build/pi-gen/deploy" ]]; then
  find "${BUILDER_DIR}/.build/pi-gen/deploy" -type f \( -name '*.log' -o -name '*.txt' \) \
    -exec cp -v {} "$LOG_DIR/" \; 2>/dev/null || true
fi
if [[ -d "${BUILDER_DIR}/.build/pi-gen/work" ]]; then
  find "${BUILDER_DIR}/.build/pi-gen/work" -type f -name 'build.log' \
    -exec cp -v {} "$LOG_DIR/" \; 2>/dev/null || true
fi
# Docker container logs (PRESERVE_CONTAINER=1)
if command -v docker >/dev/null 2>&1; then
  docker ps -a --format '{{.ID}} {{.Names}}' | while read -r id name; do
    case "$name" in
      *pi-gen*|*pigen*)
        docker logs "$id" >"$LOG_DIR/docker-${name}.log" 2>&1 || true
        ;;
    esac
  done || true
fi

echo "==> Locating images in ${OUT_DIR}"
shopt -s nullglob
imgs=( "$OUT_DIR"/*.img )
xzs=( "$OUT_DIR"/*.img.xz )
shopt -u nullglob

IMG=""
XZ=""

if ((${#xzs[@]} > 0)); then
  # Prefer the newest xz
  XZ="$(ls -1t "${xzs[@]}" | head -n1)"
  echo "Found compressed image: $XZ"
fi

if ((${#imgs[@]} > 0)); then
  IMG="$(ls -1t "${imgs[@]}" | head -n1)"
  echo "Found raw image: $IMG"
  if [[ -z "$XZ" ]]; then
    XZ="${IMG}.xz"
    echo "Compressing ${IMG} -> ${XZ}"
    xz -T0 -9 -k -f -v "$IMG"
  fi
fi

if [[ -z "$XZ" || ! -f "$XZ" ]]; then
  echo "ERROR: No .img or .img.xz found under ${OUT_DIR}"
  find "$OUT_DIR" -maxdepth 2 -printf '%p %s\n' 2>/dev/null || true
  exit 1
fi

# Canonical artifact names
VERSION="$(tr -d '\r' <"${BUILDER_DIR}/VERSION" | head -n1)"
BASE="MineBox_OS_Prototype_v1.0_RPi5"
# Keep original basename too; also publish a stable name
STABLE_XZ="${OUT_DIR}/${BASE}.img.xz"
if [[ "$(realpath "$XZ")" != "$(realpath "$STABLE_XZ")" ]]; then
  cp -v "$XZ" "$STABLE_XZ"
fi
XZ="$STABLE_XZ"

echo "==> Writing checksums"
(
  cd "$OUT_DIR"
  sha256sum "$(basename "$XZ")" >SHA256SUMS
  if [[ -n "$IMG" && -f "$IMG" ]]; then
    sha256sum "$(basename "$IMG")" >>SHA256SUMS || true
  fi
  cat SHA256SUMS
)

# Export paths for GitHub Actions
{
  echo "image_xz=$(realpath "$XZ")"
  echo "image_xz_name=$(basename "$XZ")"
  echo "sha256sums=$(realpath "$OUT_DIR/SHA256SUMS")"
  echo "version=${VERSION}"
  if [[ -n "$IMG" && -f "$IMG" ]]; then
    echo "image_raw=$(realpath "$IMG")"
    echo "image_raw_name=$(basename "$IMG")"
  fi
} | tee "${ART_DIR}/artifact-paths.env"

# Also write GITHUB_OUTPUT if present
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  cat "${ART_DIR}/artifact-paths.env" >>"$GITHUB_OUTPUT"
fi

echo "Post-process complete."
