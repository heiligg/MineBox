#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    echo "MineBox development environment is missing."
    echo "Run: ./setup-dev.sh"
    exit 1
fi

cd "${ROOT_DIR}"
export PYTHONPATH="${ROOT_DIR}/app"
export MINEBOX_DEV_MODE="${MINEBOX_DEV_MODE:-1}"
export MINEBOX_MINECRAFT_ROOT="${MINEBOX_MINECRAFT_ROOT:-${ROOT_DIR}/runtime/minecraft}"
mkdir -p "${MINEBOX_MINECRAFT_ROOT}"
exec "${VENV_DIR}/bin/python" -m uvicorn api.server:app \
    --host 0.0.0.0 \
    --port "${MINEBOX_DASHBOARD_PORT:-8080}" \
    "$@"
