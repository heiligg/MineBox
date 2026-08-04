#!/usr/bin/env bash
# MineBox idempotent appliance installer (Checkpoint 7).
# Safe to re-run. Preserves /opt/minecraft worlds/backups and /var/lib/minebox.
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="${MINEBOX_TARGET_DIR:-/opt/minebox}"
MINECRAFT_ROOT="/opt/minecraft"
MINEBOX_USER="minebox"
MINECRAFT_USER="minecraft"
SHARED_GROUP="minebox"
SUDOERS_SRC="$SOURCE_DIR/services/sudoers/minebox"
SUDOERS_FILE="/etc/sudoers.d/minebox"
DRY_RUN=0
UNINSTALL=0
SKIP_PACKAGES=0
ENABLE_DISPLAY=1

usage() {
  cat <<'USAGE'
Usage: sudo bash install.sh [options]

Options:
  --dry-run          Print actions without changing the system
  --uninstall        Disable MineBox units; preserve /opt/minecraft and /var/lib/minebox
  --skip-packages    Do not apt-get install packages
  --no-display       Do not enable minebox-display.service
  -h, --help         Show this help
USAGE
}

log() { echo "[minebox-install] $*"; }
VERSION_FILE="$SOURCE_DIR/VERSION"
if [[ -f "$VERSION_FILE" ]]; then
  MINEBOX_VERSION="$(head -n1 "$VERSION_FILE" | tr -d '\r')"
else
  MINEBOX_VERSION="unknown"
fi
log "MineBox installer version ${MINEBOX_VERSION}"
run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "DRY-RUN: $*"
    return 0
  fi
  "$@"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --skip-packages) SKIP_PACKAGES=1 ;;
    --no-display) ENABLE_DISPLAY=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 2 ;;
  esac
  shift
done

if [[ "${EUID}" -ne 0 && "$DRY_RUN" -eq 0 ]]; then
  echo "Run with: sudo bash install.sh"
  exit 1
fi

if [[ "$UNINSTALL" -eq 1 ]]; then
  log "Uninstalling MineBox services (preserving user data)"
  for unit in minebox-display minebox-ui minebox-captive minebox-api minebox-update \
              minebox-maintenance.timer minebox-maintenance minebox minebox-network; do
    run systemctl disable --now "${unit}.service" 2>/dev/null || true
    run systemctl disable --now "${unit}" 2>/dev/null || true
  done
  log "Left in place: $MINECRAFT_ROOT , /var/lib/minebox , $TARGET_DIR (files)"
  log "Uninstall complete."
  exit 0
fi

PACKAGES=(
  python3 python3-pip python3-psutil python3-jinja2
  default-jre-headless acl sudo rsync curl ca-certificates git
  network-manager openssh-server zip unzip
  hostapd dnsmasq nftables
  avahi-daemon
  chromium
  xinit x11-xserver-utils
  openbox
  plymouth plymouth-themes
)

if [[ "$SKIP_PACKAGES" -eq 0 ]]; then
  if command -v apt-get >/dev/null 2>&1; then
    log "Installing/updating packages (idempotent apt-get)"
    export DEBIAN_FRONTEND=noninteractive
    run apt-get update -y
    run apt-get install -y --no-install-recommends "${PACKAGES[@]}" || {
      log "WARN: some packages failed (chromium package name may differ); continuing"
      run apt-get install -y --no-install-recommends chromium-browser 2>/dev/null || true
    }
  else
    log "WARN: apt-get not available; --skip-packages implied"
  fi
fi

# Users / groups
getent group "$SHARED_GROUP" >/dev/null 2>&1 || run groupadd "$SHARED_GROUP"
if ! id "$MINEBOX_USER" >/dev/null 2>&1; then
  run useradd -m -s /bin/bash -G "$SHARED_GROUP" "$MINEBOX_USER"
fi
if ! id "$MINECRAFT_USER" >/dev/null 2>&1; then
  run useradd -r -s /usr/sbin/nologin -G "$SHARED_GROUP" "$MINECRAFT_USER" || \
    run useradd -m -s /bin/bash -G "$SHARED_GROUP" "$MINECRAFT_USER"
fi
run usermod -aG "$SHARED_GROUP" "$MINEBOX_USER" || true
run usermod -aG "$SHARED_GROUP" "$MINECRAFT_USER" || true
for grp in video input render gpio; do
  getent group "$grp" >/dev/null 2>&1 && run usermod -aG "$grp" "$MINEBOX_USER" || true
done

# Directories
run mkdir -p "$TARGET_DIR" \
  "$MINECRAFT_ROOT"/{server,servers,metadata,backups} \
  /var/lib/minebox /var/log/minebox /etc/minebox

# Preserve runtime state: copy tree but never wipe /var/lib/minebox or worlds
log "Syncing application tree to $TARGET_DIR"
if [[ "$DRY_RUN" -eq 1 ]]; then
  log "DRY-RUN: rsync $SOURCE_DIR/ -> $TARGET_DIR/"
else
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude '__pycache__/' \
      --exclude '*.pyc' \
      --exclude '.git/' \
      --exclude '.test-runtime/' \
      --exclude '.dev-runtime/' \
      "$SOURCE_DIR"/ "$TARGET_DIR"/
  else
    cp -a "$SOURCE_DIR"/. "$TARGET_DIR"/
  fi
fi

run chown -R "$MINEBOX_USER:$SHARED_GROUP" "$TARGET_DIR"
run chmod -R u=rwX,g=rX,o=rX "$TARGET_DIR"
run find "$TARGET_DIR/scripts" -type f \( -name '*.sh' -o -name '*.py' \) -exec chmod 0755 {} +
run chown -R "$MINECRAFT_USER:$SHARED_GROUP" "$MINECRAFT_ROOT"
run find "$MINECRAFT_ROOT" -type d -exec chmod 2775 {} +
run find "$MINECRAFT_ROOT" -type f -exec chmod 0664 {} + 2>/dev/null || true
run chown -R "$MINEBOX_USER:$SHARED_GROUP" /var/lib/minebox /var/log/minebox

if command -v setfacl >/dev/null 2>&1; then
  run setfacl -R -m "u:${MINEBOX_USER}:rwX,u:${MINECRAFT_USER}:rwX,g:${SHARED_GROUP}:rwX" "$MINECRAFT_ROOT"
  run setfacl -R -d -m "u:${MINEBOX_USER}:rwX,u:${MINECRAFT_USER}:rwX,g:${SHARED_GROUP}:rwX,m::rwX" "$MINECRAFT_ROOT"
fi

# Example config if missing
if [[ ! -f /etc/minebox/minebox.toml && -f "$TARGET_DIR/../config/minebox.example.toml" ]]; then
  run cp "$TARGET_DIR/../config/minebox.example.toml" /etc/minebox/minebox.toml || true
fi
# When app is at /opt/minebox, examples may live beside builder; also copy from TARGET if present
if [[ ! -f /etc/minebox/minebox.toml ]]; then
  for cand in \
    "$SOURCE_DIR/../config/minebox.example.toml" \
    "$TARGET_DIR/config/minebox.example.toml"; do
    if [[ -f "$cand" ]]; then
      run install -m 0644 "$cand" /etc/minebox/minebox.toml
      break
    fi
  done
fi

# Python deps
if [[ -f "$TARGET_DIR/requirements.txt" ]] && command -v pip3 >/dev/null 2>&1; then
  log "Installing Python requirements"
  run pip3 install --break-system-packages -r "$TARGET_DIR/requirements.txt" || \
    run pip3 install -r "$TARGET_DIR/requirements.txt" || true
fi

# Sudoers (single source)
if [[ -f "$SUDOERS_SRC" ]]; then
  run install -m 0440 "$SUDOERS_SRC" "$SUDOERS_FILE"
elif [[ -f "$TARGET_DIR/services/sudoers/minebox" ]]; then
  run install -m 0440 "$TARGET_DIR/services/sudoers/minebox" "$SUDOERS_FILE"
fi
if command -v visudo >/dev/null 2>&1 && [[ "$DRY_RUN" -eq 0 ]]; then
  visudo -cf "$SUDOERS_FILE"
fi

# Helpers
[[ -f "$TARGET_DIR/scripts/minebox_ensure_tls.py" ]] && \
  run install -m 0755 "$TARGET_DIR/scripts/minebox_ensure_tls.py" /usr/local/sbin/minebox-ensure-tls
[[ -f "$TARGET_DIR/scripts/minebox_api_run.py" ]] && run chmod 0755 "$TARGET_DIR/scripts/minebox_api_run.py"

# Minecraft umask drop-in
run mkdir -p /etc/systemd/system/minecraft.service.d
if [[ "$DRY_RUN" -eq 0 ]]; then
  cat >/etc/systemd/system/minecraft.service.d/minebox-permissions.conf <<'OVERRIDE'
[Service]
UMask=0002
OVERRIDE
fi

# Units
install_unit() {
  local src="$1"
  local name
  name="$(basename "$src")"
  [[ -f "$src" ]] || return 0
  run install -m 0644 "$src" "/etc/systemd/system/$name"
}

install_unit "$TARGET_DIR/services/minebox-api.service"
install_unit "$TARGET_DIR/services/minebox-captive.service"
install_unit "$TARGET_DIR/services/minebox-update.service"
install_unit "$TARGET_DIR/services/minebox-maintenance.service"
install_unit "$TARGET_DIR/services/minebox-maintenance.timer"
install_unit "$TARGET_DIR/services/minebox-display.service"
install_unit "$TARGET_DIR/services/minecraft.service"
install_unit "$TARGET_DIR/services/minebox-ui.service"
install_unit "$TARGET_DIR/services/minebox.service"

if [[ -f "$TARGET_DIR/services/polkit/10-minebox-networkmanager.rules" ]]; then
  run install -d /etc/polkit-1/rules.d
  run install -m 0644 "$TARGET_DIR/services/polkit/10-minebox-networkmanager.rules" \
    /etc/polkit-1/rules.d/10-minebox-networkmanager.rules
fi

# Hotspot templates → live configs (dynamic iface)
if [[ -f "$TARGET_DIR/scripts/minebox_render_hotspot_configs.py" ]]; then
  log "Rendering hotspot configs from interface roles"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    PYTHONPATH="$TARGET_DIR" python3 "$TARGET_DIR/scripts/minebox_render_hotspot_configs.py" --dry-run || true
  else
    PYTHONPATH="$TARGET_DIR" python3 "$TARGET_DIR/scripts/minebox_render_hotspot_configs.py" || true
  fi
fi

# Plymouth theme (best-effort)
THEME_SRC="$TARGET_DIR/boot/minebox-plymouth-theme"
if [[ -d "$THEME_SRC" ]] && command -v plymouth-set-default-theme >/dev/null 2>&1; then
  run mkdir -p /usr/share/plymouth/themes/minebox
  run cp -a "$THEME_SRC"/. /usr/share/plymouth/themes/minebox/ || true
  run plymouth-set-default-theme minebox || true
fi

# Disable legacy NM hotspot guard
run systemctl disable --now minebox-network.service >/dev/null 2>&1 || true
run rm -f /etc/systemd/system/minebox-network.service

run systemctl daemon-reload

# Enable appliance services
enable_now() {
  local unit="$1"
  run systemctl enable "$unit" >/dev/null 2>&1 || true
}

enable_now minebox-api.service
enable_now minebox-captive.service
enable_now minebox-maintenance.timer
enable_now minebox-update.service
enable_now hostapd.service
enable_now dnsmasq.service
enable_now nftables.service
# Curses recovery UI
if [[ -f /etc/systemd/system/minebox-ui.service ]]; then
  enable_now minebox-ui.service
fi
# Minecraft unit enabled but StartLimit protects empty installs
enable_now minecraft.service

if [[ "$ENABLE_DISPLAY" -eq 1 ]]; then
  if command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1; then
    if command -v xinit >/dev/null 2>&1; then
      enable_now minebox-display.service
      log "Enabled minebox-display (Chromium kiosk)"
    else
      log "WARN: xinit missing; display unit not enabled (curses fallback remains)"
    fi
  else
    log "WARN: Chromium missing; display unit not enabled (curses fallback remains)"
  fi
fi

# Do not enable bare minebox.service (curses via minebox-ui on tty1)
run systemctl disable minebox.service >/dev/null 2>&1 || true

if [[ "$DRY_RUN" -eq 0 ]]; then
  systemctl restart minebox-api.service 2>/dev/null || systemctl start minebox-api.service 2>/dev/null || true
  if systemctl is-active --quiet minecraft.service; then
    systemctl restart minecraft.service || true
  fi
  PYTHONPATH="$TARGET_DIR" python3 "$TARGET_DIR/scripts/minebox_validate_install.py" || true
fi

log "MineBox install complete."
log "User data preserved under $MINECRAFT_ROOT and /var/lib/minebox."
log "Complete first-boot over SoftAP: http://192.168.4.1"
log "Recovery console: minebox-ui on tty1 (curses)."
