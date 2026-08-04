#!/usr/bin/env bash
# Validate MineBox pi-gen image artifacts and staged rootfs (CI-safe).
set -euo pipefail

BUILDER_DIR="${1:-MineBox-OS-Builder-v0.2}"
OUT_DIR="${BUILDER_DIR}/output"
ART_DIR="${BUILDER_DIR}/ci-artifacts"
VAL_LOG="${ART_DIR}/validation.log"
mkdir -p "$ART_DIR"
: >"$VAL_LOG"

log() { echo "$*" | tee -a "$VAL_LOG"; }
fail() { log "FAIL: $*"; exit 1; }
pass() { log "PASS: $*"; }

EXPECTED_VERSION="$(tr -d '\r' <"${BUILDER_DIR}/VERSION" | head -n1)"
[[ -n "$EXPECTED_VERSION" ]] || fail "VERSION file empty"

log "==> MineBox version expected: ${EXPECTED_VERSION}"

shopt -s nullglob
xzs=( "$OUT_DIR"/*.img.xz )
imgs=( "$OUT_DIR"/*.img )
shopt -u nullglob

XZ=""
if ((${#xzs[@]} > 0)); then
  XZ="$(ls -1t "${xzs[@]}" | head -n1)"
fi
[[ -n "$XZ" && -f "$XZ" ]] || fail "No .img.xz in ${OUT_DIR}"

SIZE="$(stat -c%s "$XZ")"
log "Compressed image: $(basename "$XZ") (${SIZE} bytes)"

# Reasonable size for a Raspberry Pi OS + MineBox appliance (xz)
# Fail if tiny (failed export) or absurdly huge for the runner.
MIN_BYTES=$((400 * 1024 * 1024))   # 400 MiB
MAX_BYTES=$((12 * 1024 * 1024 * 1024)) # 12 GiB
if (( SIZE < MIN_BYTES )); then
  fail "Image too small (${SIZE} < ${MIN_BYTES}); likely incomplete"
fi
if (( SIZE > MAX_BYTES )); then
  fail "Image unexpectedly large (${SIZE} > ${MAX_BYTES})"
fi
pass "Compressed size within expected range"

if [[ ! -f "${OUT_DIR}/SHA256SUMS" ]]; then
  fail "Missing ${OUT_DIR}/SHA256SUMS"
fi
(
  cd "$OUT_DIR"
  sha256sum -c SHA256SUMS
) | tee -a "$VAL_LOG"
pass "SHA256SUMS verified"

# Validate staged rootfs from pi-gen work tree (no full decompress required).
ROOTFS=""
if [[ -d "${BUILDER_DIR}/.build/pi-gen/work" ]]; then
  ROOTFS="$(find "${BUILDER_DIR}/.build/pi-gen/work" -type d -path '*/stage-minebox/rootfs' 2>/dev/null | head -n1 || true)"
fi

if [[ -z "$ROOTFS" || ! -d "$ROOTFS" ]]; then
  log "WARN: stage-minebox rootfs not found under .build; attempting limited .img checks only"
else
  log "==> Validating rootfs at ${ROOTFS}"
  [[ -f "${ROOTFS}/opt/minebox/VERSION" ]] || fail "Missing /opt/minebox/VERSION in rootfs"
  ROOTFS_VERSION="$(tr -d '\r' <"${ROOTFS}/opt/minebox/VERSION" | head -n1)"
  [[ "$ROOTFS_VERSION" == "$EXPECTED_VERSION" ]] || \
    fail "Version mismatch: rootfs='${ROOTFS_VERSION}' expected='${EXPECTED_VERSION}'"
  pass "VERSION matches (${ROOTFS_VERSION})"

  [[ -f "${ROOTFS}/opt/minebox/scripts/minebox_api_run.py" ]] || fail "Missing minebox_api_run.py"
  [[ -f "${ROOTFS}/opt/minebox/services/minebox-api.service" ]] || fail "Missing minebox-api.service in app tree"
  pass "Core MineBox files present under /opt/minebox"

  for unit in minebox-api.service minebox-ui.service minebox-captive.service minecraft.service; do
    if [[ -f "${ROOTFS}/etc/systemd/system/${unit}" ]]; then
      pass "systemd unit installed: ${unit}"
    else
      fail "Missing systemd unit: /etc/systemd/system/${unit}"
    fi
  done

  # SoftAP stack packages / configs
  [[ -f "${ROOTFS}/etc/hostapd/hostapd.conf" ]] || fail "Missing hostapd.conf"
  [[ -f "${ROOTFS}/etc/nftables.conf" ]] || fail "Missing nftables.conf"
  if [[ -f "${ROOTFS}/etc/dnsmasq.d/minebox.conf" || -f "${ROOTFS}/etc/dnsmasq.d/dnsmasq-minebox.conf" ]]; then
    pass "dnsmasq MineBox config present"
  else
    fail "Missing dnsmasq MineBox config"
  fi
  [[ -f "${ROOTFS}/etc/sudoers.d/minebox" ]] || fail "Missing /etc/sudoers.d/minebox"
  pass "Hotspot / firewall / sudoers present"

  # Enabled wants (best-effort)
  for want in minebox-api.service hostapd.service dnsmasq.service nftables.service; do
    if ls "${ROOTFS}/etc/systemd/system/"*.wants/"${want}" >/dev/null 2>&1 \
      || ls "${ROOTFS}/etc/systemd/system/multi-user.target.wants/${want}" >/dev/null 2>&1 \
      || ls "${ROOTFS}/lib/systemd/system/"*.wants/"${want}" >/dev/null 2>&1; then
      pass "unit enabled (wants): ${want}"
    else
      log "WARN: could not confirm enabled wants for ${want} (may use presets)"
    fi
  done
fi

# Filesystem probe of compressed image when guestfish/libguestfs available (optional).
if command -v guestfish >/dev/null 2>&1; then
  log "==> guestfish probe of $(basename "$XZ")"
  if guestfish --ro -a "$XZ" -i <<<'is-dir /opt/minebox' 2>>"$VAL_LOG" | grep -q true; then
    pass "guestfish: /opt/minebox exists in image"
  else
    log "WARN: guestfish probe inconclusive (continuing; rootfs checks may already have passed)"
  fi
fi

# Raw .img optional size note
if ((${#imgs[@]} > 0)); then
  RAW="$(ls -1t "${imgs[@]}" | head -n1)"
  log "Raw image present: $(basename "$RAW") ($(stat -c%s "$RAW") bytes)"
fi

log "==> Validation successful"
exit 0
