#!/bin/bash
# Run script for Daily Ladder Bot backend (background mode)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

HOME_VENV_PYTHON="$HOME/.venvs/ema_bot/bin/python"
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

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Backend is already running (PID $OLD_PID)"
        echo "Run ./stop_backend.sh to stop it first"
        exit 1
    fi
    rm -f "$PID_FILE"
fi

# Get local IP address
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo "Starting Daily Ladder Bot Backend (background)..."
echo "======================================="
echo ""
echo "Access URLs:"
echo "  Local:      http://localhost:8010"
if [ -n "$LOCAL_IP" ]; then
    echo "  Network:    http://$LOCAL_IP:8010"
fi
echo "  API docs:   http://localhost:8010/docs"
echo ""
echo "Logs:    $LOG_FILE"
echo "To stop: ./stop_backend.sh"
echo ""

nohup setsid "$PYTHON_BIN" -m uvicorn \
    --app-dir "$PROJECT_ROOT/backend" \
    app.main:app \
    --host 0.0.0.0 \
    --port 8010 \
    >> "$LOG_FILE" 2>&1 < /dev/null &
echo $! > "$PID_FILE"

BACKEND_PID=$(cat "$PID_FILE")
sleep 3

if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Backend failed to stay running. Recent log output:"
    tail -n 50 "$LOG_FILE" 2>/dev/null || true
    rm -f "$PID_FILE"
    exit 1
fi

if ! curl -fsS "http://127.0.0.1:8010/" >/dev/null 2>&1; then
    echo "Backend process started but HTTP endpoint did not become ready. Recent log output:"
    tail -n 50 "$LOG_FILE" 2>/dev/null || true
    exit 1
fi

echo "Backend started (PID $BACKEND_PID)"
