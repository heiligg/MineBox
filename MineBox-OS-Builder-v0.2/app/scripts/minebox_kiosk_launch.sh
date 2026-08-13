#!/bin/bash
# MineBox Chromium kiosk launcher (800×480 local display).
set -euo pipefail

DISPLAY_URL="${MINEBOX_DISPLAY_URL:-http://127.0.0.1:8080/display}"
PROFILE_DIR="${MINEBOX_KIOSK_PROFILE:-/var/lib/minebox/chromium-kiosk}"
TOKEN_FILE="${MINEBOX_DISPLAY_TOKEN_FILE:-/var/lib/minebox/display_token}"
API="${MINEBOX_API_BASE:-http://127.0.0.1:8080}"

mkdir -p "$PROFILE_DIR"
chmod 700 "$PROFILE_DIR" 2>/dev/null || true

# Disable screen blanking / DPMS for appliance use (best-effort).
if command -v xset >/dev/null 2>&1; then
  xset s off >/dev/null 2>&1 || true
  xset -dpms >/dev/null 2>&1 || true
  xset s noblank >/dev/null 2>&1 || true
fi

# Hide the mouse pointer for the appliance panel (no pointer interaction).
hide_cursor() {
  local blank="${MINEBOX_KIOSK_PROFILE:-/var/lib/minebox/chromium-kiosk}/blank_cursor.xbm"
  mkdir -p "$(dirname "$blank")" 2>/dev/null || true
  cat >"$blank" <<'EOF'
#define blank_width 1
#define blank_height 1
static unsigned char blank_bits[] = { 0x00 };
EOF
  if command -v xsetroot >/dev/null 2>&1; then
    xsetroot -cursor "$blank" "$blank" >/dev/null 2>&1 || true
  fi
  if command -v unclutter-xfixes >/dev/null 2>&1; then
    unclutter-xfixes --timeout 0 --jitter 0 --hide-on-touch --start-hidden >/dev/null 2>&1 &
  elif command -v unclutter >/dev/null 2>&1; then
    unclutter -idle 0 -root -noevents >/dev/null 2>&1 &
  fi
  if command -v xdotool >/dev/null 2>&1; then
    # Park any residual pointer off the 800x480 panel.
    xdotool mousemove 900 500 >/dev/null 2>&1 || true
  fi
}
hide_cursor

# Wait for backend health without a long fixed sleep primary path.
for _ in $(seq 1 60); do
  if curl -fsS "$API/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Establish loopback display session cookie in the kiosk profile via curl + Chromium cookie is hard;
# instead ensure token file exists and POST session (Chromium will call session on load too).
if [[ ! -f "$TOKEN_FILE" ]]; then
  umask 077
  head -c 48 /dev/urandom | base64 | tr -d '\n=' >"$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE" || true
fi
TOKEN="$(tr -d '[:space:]' <"$TOKEN_FILE")"
curl -fsS -X POST \
  -H "X-MineBox-Display-Token: ${TOKEN}" \
  -c "${PROFILE_DIR}/display-cookies.txt" \
  "${API}/api/v1/display/session" >/dev/null 2>&1 || true

CHROME=""
for candidate in chromium-browser chromium google-chrome; do
  if command -v "$candidate" >/dev/null 2>&1; then
    CHROME="$candidate"
    break
  fi
done

if [[ -z "$CHROME" ]]; then
  echo "minebox-kiosk: Chromium not installed" >&2
  exit 1
fi

# Kiosk flags: no chrome UI, no first-run, no password manager, no crash bubble.
exec "$CHROME" \
  --user-data-dir="$PROFILE_DIR" \
  --kiosk \
  --window-size=800,480 \
  --window-position=0,0 \
  --noerrdialogs \
  --disable-session-crashed-bubble \
  --disable-infobars \
  --disable-translate \
  --disable-features=TranslateUI \
  --disable-save-password-bubble \
  --password-store=basic \
  --no-first-run \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  --check-for-update-interval=31536000 \
  --autoplay-policy=no-user-gesture-required \
  --app="$DISPLAY_URL"
