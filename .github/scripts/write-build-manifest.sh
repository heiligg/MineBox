#!/usr/bin/env bash
# Write CI build manifest JSON for MineBox image artifacts.
set -euo pipefail

BUILDER_DIR="${1:-MineBox-OS-Builder-v0.2}"
OUT_DIR="${BUILDER_DIR}/output"
ART_DIR="${BUILDER_DIR}/ci-artifacts"
mkdir -p "$ART_DIR"

VERSION="$(tr -d '\r' <"${BUILDER_DIR}/VERSION" | head -n1)"
COMMIT="${GITHUB_SHA:-$(git rev-parse HEAD 2>/dev/null || echo unknown)}"
RUN_ID="${GITHUB_RUN_ID:-local}"
SERVER="${GITHUB_SERVER_URL:-https://github.com}"
REPO="${GITHUB_REPOSITORY:-local/MineBox}"
RUN_URL="${SERVER}/${REPO}/actions/runs/${RUN_ID}"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

XZ="$(ls -1t "$OUT_DIR"/*.img.xz 2>/dev/null | head -n1 || true)"
[[ -n "$XZ" && -f "$XZ" ]] || { echo "ERROR: no .img.xz for manifest"; exit 1; }
XZ_NAME="$(basename "$XZ")"
SHA="$(sha256sum "$XZ" | awk '{print $1}')"
SIZE="$(stat -c%s "$XZ")"

RAW_NAME=""
if ls "$OUT_DIR"/*.img >/dev/null 2>&1; then
  RAW_NAME="$(basename "$(ls -1t "$OUT_DIR"/*.img | head -n1)")"
fi

BASE_OS="$(grep -E '^RELEASE=' "${BUILDER_DIR}/config/minebox-pi5.conf" | head -n1 | cut -d= -f2 | tr -d "'\"")"
IMG_NAME="$(grep -E '^IMG_NAME=' "${BUILDER_DIR}/config/minebox-pi5.conf" | head -n1 | cut -d= -f2 | tr -d "'\"")"

python3 - "$ART_DIR/build-manifest.json" <<PY
import json, sys
from pathlib import Path

raw_name = """${RAW_NAME}""".strip()
manifest = {
    "product_name": "MineBox OS Prototype",
    "minebox_version": """${VERSION}""",
    "git_commit": """${COMMIT}""",
    "workflow_run_id": """${RUN_ID}""",
    "github_actions_url": """${RUN_URL}""",
    "timestamp": """${TS}""",
    "base_raspberry_pi_os": """${BASE_OS}""",
    "pi_target": "Raspberry Pi 5",
    "img_name": """${IMG_NAME}""",
    "image_filename": raw_name or None,
    "compressed_filename": """${XZ_NAME}""",
    "compressed_size_bytes": ${SIZE},
    "sha256": """${SHA}""",
    "included_services": [
        "minebox-api.service",
        "minebox-ui.service",
        "minebox-captive.service",
        "minebox-display.service",
        "minecraft.service",
        "hostapd.service",
        "dnsmasq.service",
        "nftables.service",
        "NetworkManager.service",
        "systemd-networkd.service",
    ],
    "deploy_compression": "xz",
    "builder_path": """${BUILDER_DIR}""",
}
Path(sys.argv[1]).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps(manifest, indent=2))
PY

# Mirror into output for artifact upload convenience
cp -v "${ART_DIR}/build-manifest.json" "${OUT_DIR}/build-manifest.json"
