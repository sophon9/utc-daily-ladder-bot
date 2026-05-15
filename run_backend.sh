#!/bin/bash
# Run script for EMA Trading Bot backend (background mode)

cd "$(dirname "$0")"

HOME_VENV_PYTHON="$HOME/.venvs/ema_bot/bin/python"
LOCAL_VENV_PYTHON="$(pwd)/backend/venv/bin/python"

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
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found!"
    echo "Please copy .env.example to .env and configure your API credentials"
    exit 1
fi

# Check if config.json exists
if [ ! -f "config.json" ]; then
    echo "Warning: config.json not found!"
    echo "Copying from config.example.json..."
    cp config.example.json config.json
fi

# Create directories
mkdir -p logs data

PID_FILE="logs/backend.pid"
LOG_FILE="logs/backend.log"

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

echo "Starting EMA Trading Bot Backend (background)..."
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

cd backend
nohup "$PYTHON_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8010 >> "../$LOG_FILE" 2>&1 &
echo $! > "../$PID_FILE"

echo "Backend started (PID $(cat ../$PID_FILE))"
