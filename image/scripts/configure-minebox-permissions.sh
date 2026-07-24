#!/usr/bin/env bash
set -Eeuo pipefail

MINEBOX_USER="${MINEBOX_USER:-minebox}"
MINEBOX_GROUP="${MINEBOX_GROUP:-minebox}"

# The installed Git repository must be inside a parent directory writable by
# minebox because the transactional updater creates sibling .update,
# .previous, .failed, and .data directories.
MINEBOX_RELEASE_ROOT="${MINEBOX_RELEASE_ROOT:-/opt/minebox-releases}"
MINEBOX_REPO="${MINEBOX_REPO:-${MINEBOX_RELEASE_ROOT}/current}"

MINEBOX_DATA="${MINEBOX_DATA:-/var/lib/minebox}"
MINEBOX_LOG="${MINEBOX_LOG:-/var/log/minebox}"
MINEBOX_CONFIG="${MINEBOX_CONFIG:-/etc/minebox}"

echo "Configuring MineBox users and permissions..."

if ! id "${MINEBOX_USER}" >/dev/null 2>&1; then
    useradd \
        --create-home \
        --shell /bin/bash \
        --user-group \
        "${MINEBOX_USER}"
fi

# Add only groups that exist on this image.
for group in gpio i2c spi video render dialout netdev input; do
    if getent group "${group}" >/dev/null 2>&1; then
        usermod -aG "${group}" "${MINEBOX_USER}"
    fi
done

install -d -o "${MINEBOX_USER}" -g "${MINEBOX_GROUP}" -m 0755 \
    "${MINEBOX_RELEASE_ROOT}"

install -d -o "${MINEBOX_USER}" -g "${MINEBOX_GROUP}" -m 0750 \
    "${MINEBOX_DATA}" \
    "${MINEBOX_DATA}/runtime" \
    "${MINEBOX_DATA}/updates" \
    "${MINEBOX_LOG}"

install -d -o root -g "${MINEBOX_GROUP}" -m 0750 \
    "${MINEBOX_CONFIG}"

if [[ -d "${MINEBOX_REPO}" ]]; then
    chown -R "${MINEBOX_USER}:${MINEBOX_GROUP}" "${MINEBOX_REPO}"

    # Do not force every file executable. Preserve Git's executable flags and
    # explicitly enable the launch/update scripts MineBox needs.
    [[ -f "${MINEBOX_REPO}/run-dashboard.sh" ]] &&
        chmod 0755 "${MINEBOX_REPO}/run-dashboard.sh"

    if [[ -d "${MINEBOX_REPO}/app/scripts" ]]; then
        find "${MINEBOX_REPO}/app/scripts" \
            -maxdepth 1 \
            -type f \
            -name '*.py' \
            -exec chmod 0755 {} +
    fi
fi

# Clean old image-builder output out of the installed release. It must not be
# included in transactional application swaps.
if [[ -d "${MINEBOX_REPO}/.build" ]]; then
    rm -rf "${MINEBOX_REPO}/.build"
fi

# Allow the dashboard to perform only these specific system actions without
# giving it unrestricted passwordless root access.
cat > /etc/sudoers.d/minebox <<SUDOERS
${MINEBOX_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart minebox-api.service
${MINEBOX_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl start minebox-api.service
${MINEBOX_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl stop minebox-api.service
${MINEBOX_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart NetworkManager.service
${MINEBOX_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl reboot
${MINEBOX_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff
SUDOERS

chown root:root /etc/sudoers.d/minebox
chmod 0440 /etc/sudoers.d/minebox

if command -v visudo >/dev/null 2>&1; then
    visudo -cf /etc/sudoers.d/minebox
fi

echo
echo "MineBox permissions configured."
echo "Release root: ${MINEBOX_RELEASE_ROOT}"
echo "Repository:   ${MINEBOX_REPO}"
echo "Data:         ${MINEBOX_DATA}"
echo "Logs:         ${MINEBOX_LOG}"
