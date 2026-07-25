#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

if [[ "${ROOT_DIR}" == /media/sf_* ]]; then
    echo "VirtualBox shared folders cannot reliably host Python virtual environments."
    echo "Copy the whole MineBox folder into your Linux home directory first:"
    echo "  cp -a '${ROOT_DIR}' ~/MineBox-OS-Builder-v0.2"
    exit 1
fi

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${ROOT_DIR}/requirements.txt"

echo
echo "MineBox dashboard environment is ready."
echo "Start it with: ./run-dashboard.sh --reload"
