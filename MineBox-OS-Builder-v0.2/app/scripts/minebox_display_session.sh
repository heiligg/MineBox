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
  # Hide pointer as soon as the X session is up (kiosk script also hides).
  if command -v xsetroot >/dev/null 2>&1; then
    blank="/tmp/minebox_blank_cursor.xbm"
    printf '%s\n' '#define blank_width 1' '#define blank_height 1' 'static unsigned char blank_bits[] = { 0x00 };' >"$blank"
    xsetroot -cursor "$blank" "$blank" >/dev/null 2>&1 || true
  fi
  "$KIOSK"
  kill "$OB_PID" >/dev/null 2>&1 || true
else
  exec "$KIOSK"
fi
