#!/usr/bin/env bash
# Start the complete local ATLAS stack: Ollama, FastAPI, and Vite.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}/roche-atlas-${UID}"
BACKEND_PORT="${ATLAS_BACKEND_PORT:-8000}"
FRONTEND_PORT="${ATLAS_FRONTEND_PORT:-5173}"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"

mkdir -p "${RUNTIME_DIR}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

wait_for_http() {
  local url="$1"
  local service_name="$2"

  for _ in $(seq 1 60); do
    if curl --fail --silent --show-error --max-time 2 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "${service_name} did not become ready. See ${RUNTIME_DIR}/${service_name}.log" >&2
  return 1
}

require_command curl
require_command ollama
require_command python3
require_command npm

if ! curl --fail --silent --show-error --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Starting Ollama..."
  nohup ollama serve >"${RUNTIME_DIR}/ollama.log" 2>&1 &
  echo $! >"${RUNTIME_DIR}/ollama.pid"
  wait_for_http "http://127.0.0.1:11434/api/tags" "ollama"
else
  echo "Ollama is already running."
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Creating Python virtual environment..."
  python3 -m venv "${ROOT_DIR}/.venv"
fi

if ! "${PYTHON_BIN}" -c 'import chromadb, duckduckgo_search, fastapi, httpx' >/dev/null 2>&1; then
  echo "Installing backend dependencies..."
  "${ROOT_DIR}/.venv/bin/pip" install -r "${ROOT_DIR}/backend/requirements.txt"
fi

if [[ ! -x "${ROOT_DIR}/frontend/node_modules/.bin/vite" ]]; then
  echo "Installing frontend dependencies..."
  npm --prefix "${ROOT_DIR}/frontend" ci
fi

BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}/api/rag/status"
if ! curl --fail --silent --show-error --max-time 2 "${BACKEND_URL}" >/dev/null 2>&1; then
  echo "Starting FastAPI on port ${BACKEND_PORT}..."
  (
    cd "${ROOT_DIR}/backend"
    exec "${PYTHON_BIN}" -m uvicorn app.main:app --host 0.0.0.0 --port "${BACKEND_PORT}"
  ) >"${RUNTIME_DIR}/backend.log" 2>&1 &
  echo $! >"${RUNTIME_DIR}/backend.pid"
  wait_for_http "${BACKEND_URL}" "backend"
else
  echo "FastAPI is already running on port ${BACKEND_PORT}."
fi

FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"
if ! curl --fail --silent --show-error --max-time 2 "${FRONTEND_URL}" >/dev/null 2>&1; then
  echo "Starting Vite on port ${FRONTEND_PORT}..."
  (
    cd "${ROOT_DIR}/frontend"
    exec npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT}" --strictPort
  ) >"${RUNTIME_DIR}/frontend.log" 2>&1 &
  echo $! >"${RUNTIME_DIR}/frontend.pid"
  wait_for_http "${FRONTEND_URL}" "frontend"
else
  echo "Vite is already running on port ${FRONTEND_PORT}."
fi

echo "ATLAS is ready:"
echo "  Backend:  http://127.0.0.1:${BACKEND_PORT}"
echo "  Frontend: http://127.0.0.1:${FRONTEND_PORT}"
echo "  Logs:     ${RUNTIME_DIR}"
