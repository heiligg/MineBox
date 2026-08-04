#!/bin/bash
# Starts a minimal X session and the MineBox kiosk (no full desktop).
set -euo pipefail

export DISPLAY="${DISPLAY:-:0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KIOSK="${SCRIPT_DIR}/minebox_kiosk_launch.sh"

# Prefer openbox if present; otherwise run Chromium directly under startx.
if command -v openbox >/dev/null 2>&1; then
  openbox &
  OB_PID=$!
  sleep 0.5
  "$KIOSK"
  kill "$OB_PID" >/dev/null 2>&1 || true
else
  exec "$KIOSK"
fi
