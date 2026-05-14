#!/usr/bin/env bash

set -euo pipefail

PI_HOST="${PI_HOST:-pi.local}"
PI_USER="${PI_USER:-pi}"
PI_PORT="${PI_PORT:-22}"
REMOTE_BASE_DIR="${REMOTE_BASE_DIR:-/home/${PI_USER}/secure-camera}"
REMOTE_APP_DIR="${REMOTE_BASE_DIR}/raspberry"
REMOTE_LOG_FILE="${REMOTE_APP_DIR}/raspberry.log"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[deploy] Syncing Raspberry project to ${PI_USER}@${PI_HOST}:${REMOTE_APP_DIR}"

rsync -avz --delete \
  --exclude "__pycache__" \
  --exclude ".DS_Store" \
  --exclude "*.pyc" \
  --exclude ".venv" \
  --exclude "venv" \
  --exclude "env" \
  -e "ssh -p ${PI_PORT}" \
  "${SCRIPT_DIR}/" \
  "${PI_USER}@${PI_HOST}:${REMOTE_APP_DIR}/"

echo "[deploy] Installing Python requirements on Raspberry Pi"

ssh -p "${PI_PORT}" "${PI_USER}@${PI_HOST}" \
  "mkdir -p '${REMOTE_APP_DIR}' && cd '${REMOTE_APP_DIR}' && python3 -m pip install --user -r requirements.txt"

echo "[deploy] Restarting Raspberry service"

ssh -p "${PI_PORT}" "${PI_USER}@${PI_HOST}" "
  pkill -f 'python3 app/main.py' || true
  cd '${REMOTE_APP_DIR}'
  nohup python3 app/main.py > '${REMOTE_LOG_FILE}' 2>&1 < /dev/null &
"

echo "[deploy] Done"
echo "[deploy] Health endpoint: http://${PI_HOST}:5000/api/health"
echo "[deploy] Video feed:      http://${PI_HOST}:5000/video_feed"
