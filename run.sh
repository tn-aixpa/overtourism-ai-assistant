#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Load local environment variables, if available
if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a
    source "$ROOT_DIR/.env"
    set +a
fi

# Check prerequisites
if ! command -v uv >/dev/null 2>&1; then
    printf 'Error: uv is not installed.\n' >&2
    exit 1
fi

if [[ ! -f "$ROOT_DIR/pyproject.toml" ]]; then
    printf 'Error: pyproject.toml not found in %s\n' "$ROOT_DIR" >&2
    exit 1
fi

# Create the virtual environment and install dependencies
if [[ ! -d "$ROOT_DIR/.venv" ]]; then
    uv venv "$ROOT_DIR/.venv"
fi

uv sync --locked --project "$ROOT_DIR"

# Application configuration
export BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000/api/}"
export AUTH_ENABLED="${AUTH_ENABLED:-true}"
export LLM_PROVIDER="${LLM_PROVIDER:-azure}"

# Save conversations to logs/ (state_<session>.json): true | false.
# Environment / .env value wins; defaults to false.
SAVE_CONVERSATION_LOGS="${SAVE_CONVERSATION_LOGS:-true}"
# Console log verbosity: DEBUG | INFO | WARNING | ERROR | CRITICAL.
LOG_LEVEL="${LOG_LEVEL:-INFO}"

case "${SAVE_CONVERSATION_LOGS,,}" in
    1|true|t|yes|y|on)  SAVE_CONVERSATION_LOGS=true ;;
    0|false|f|no|n|off|"") SAVE_CONVERSATION_LOGS=false ;;
    *)
        printf 'Error: SAVE_CONVERSATION_LOGS must be true or false, got: %s\n' "$SAVE_CONVERSATION_LOGS" >&2
        exit 2
        ;;
esac

LOG_LEVEL="${LOG_LEVEL^^}"
case "$LOG_LEVEL" in
    DEBUG|INFO|WARNING|ERROR|CRITICAL) ;;
    *)
        printf 'Error: LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL, got: %s\n' "$LOG_LEVEL" >&2
        exit 2
        ;;
esac
export SAVE_CONVERSATION_LOGS LOG_LEVEL

# Validate secrets required by the selected LLM provider
case "$LLM_PROVIDER" in
    azure)
        : "${AZURE_API_KEY:?AZURE_API_KEY must be configured when LLM_PROVIDER=azure}"
        : "${AZURE_ENDPOINT:?AZURE_ENDPOINT must be configured when LLM_PROVIDER=azure}"
        export AZURE_API_KEY AZURE_ENDPOINT
        ;;
    anthropic)
        : "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be configured when LLM_PROVIDER=anthropic}"
        export ANTHROPIC_API_KEY
        ;;
    *)
        printf 'Error: Unsupported LLM_PROVIDER: %s\n' "$LLM_PROVIDER" >&2
        printf 'Supported providers: azure, anthropic\n' >&2
        exit 2
        ;;
esac

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-9000}"
ENVIRONMENT="${ENVIRONMENT:-development}"

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
    printf 'Error: PORT must be between 1 and 65535.\n' >&2
    exit 2
fi

UVICORN_ARGS=(
    app.main:app
    --host "$HOST"
    --port "$PORT"
)

if [[ "$ENVIRONMENT" == "development" ]]; then
    UVICORN_ARGS+=(--reload)
fi

exec "$ROOT_DIR/.venv/bin/uvicorn" "${UVICORN_ARGS[@]}"