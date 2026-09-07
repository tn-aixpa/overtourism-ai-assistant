#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/.venv/bin/activate"

# Application configuration
export BACKEND_URL="${BACKEND_URL:-http://0.0.0.0:8000/api/v2/}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-sk-...}"
export SMARTLAB_API_KEY="${SMARTLAB_API_KEY:-sk-..}"
export AUTH_ENABLED="${AUTH_ENABLED:-true}"
export AZURE_API_KEY="${AZURE_API_KEY:-YOUR-KEY}"
export AZURE_ENDPOINT="${AZURE_ENDPOINT:-YOUR-ENDPOINT}"
export LLM_PROVIDER="${LLM_PROVIDER:-azure}"
export DISABLE_INTEGRATED="${DISABLE_INTEGRATED:-false}"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-9000}"

# Kill anything already using the port
kill -9 $(lsof -t -i:$PORT) >/dev/null 2>&1 || true

# Start the application with uvicorn
exec uvicorn app.main:app \
    --reload \
    --host "$HOST" \
    --port "$PORT"