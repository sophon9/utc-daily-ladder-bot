#!/bin/bash
# Run script for Daily Ladder Bot backend (background mode)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT=8030

HOME_VENV_PYTHON="$HOME/.venvs/utc_daily_ladder_bot/bin/python"
LOCAL_VENV_PYTHON="$PROJECT_ROOT/backend/venv/bin/python"

# Prefer a stable home-directory virtualenv so background launches do not
# depend on the calling shell's PATH or activation state.
if [ -x "$HOME_VENV_PYTHON" ]; then
    PYTHON_BIN="$HOME_VENV_PYTHON"
elif [ -x "$LOCAL_VENV_PYTHON" ]; then
    PYTHON_BIN="$LOCAL_VENV_PYTHON"
else
    echo "Error: Python virtual environment not found!"
    echo "Expected one of:"
    echo "  $HOME_VENV_PYTHON"
    echo "  $LOCAL_VENV_PYTHON"
    exit 1
fi

# Check if .env exists
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "Warning: .env file not found!"
    echo "Please copy .env.example to .env and configure your API credentials"
    exit 1
fi

# Check if config.json exists
if [ ! -f "$PROJECT_ROOT/config.json" ]; then
    echo "Warning: config.json not found!"
    echo "Copying from config.example.json..."
    cp "$PROJECT_ROOT/config.example.json" "$PROJECT_ROOT/config.json"
fi

# Create directories
mkdir -p "$PROJECT_ROOT/logs" "$PROJECT_ROOT/data"

PID_FILE="$PROJECT_ROOT/logs/backend.pid"
LOG_FILE="$PROJECT_ROOT/logs/backend.log"

is_pid_running() {
    local pid="$1"
    kill -0 "$pid" 2>/dev/null
}

get_listen_pids() {
    local port="$1"
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
}

wait_for_http() {
    local url="$1"
    local attempts="${2:-20}"
    local delay="${3:-1}"
    local i
    for ((i = 1; i <= attempts; i++)); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep "$delay"
    done
    return 1
}

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if is_pid_running "$OLD_PID"; then
        echo "Backend is already running (PID $OLD_PID)"
        echo "Run ./stop_backend.sh to stop it first"
        exit 1
    fi
    rm -f "$PID_FILE"
fi

EXISTING_PIDS="$(get_listen_pids "$PORT")"
if [ -n "$EXISTING_PIDS" ]; then
    echo "Backend is already listening on port $PORT: $EXISTING_PIDS"
    echo "Run ./stop_backend.sh to stop it first"
    exit 1
fi

# Get local IP address
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo "Starting Daily Ladder Bot Backend (background)..."
echo "======================================="
echo ""
echo "Access URLs:"
echo "  Local:      http://localhost:$PORT"
if [ -n "$LOCAL_IP" ]; then
    echo "  Network:    http://$LOCAL_IP:$PORT"
fi
echo "  API docs:   http://localhost:$PORT/docs"
echo ""
echo "Logs:    $LOG_FILE"
echo "To stop: ./stop_backend.sh"
echo ""

nohup setsid "$PYTHON_BIN" -m uvicorn \
    --app-dir "$PROJECT_ROOT/backend" \
    app.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    >> "$LOG_FILE" 2>&1 < /dev/null &
echo $! > "$PID_FILE"

BACKEND_PID=$(cat "$PID_FILE")
sleep 1

if ! is_pid_running "$BACKEND_PID"; then
    echo "Backend failed to stay running. Recent log output:"
    tail -n 50 "$LOG_FILE" 2>/dev/null || true
    rm -f "$PID_FILE"
    exit 1
fi

if ! wait_for_http "http://127.0.0.1:$PORT/" 20 1; then
    echo "Backend process started but HTTP endpoint did not become ready. Recent log output:"
    tail -n 50 "$LOG_FILE" 2>/dev/null || true
    exit 1
fi

echo "Backend started (PID $BACKEND_PID)"
