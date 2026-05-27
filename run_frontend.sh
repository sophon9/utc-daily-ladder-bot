#!/bin/bash
# Run script for Daily Ladder Bot frontend (background mode)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT=3030

# Check if node_modules exists
if [ ! -d "$PROJECT_ROOT/frontend/node_modules" ]; then
    echo "Error: node_modules not found!"
    echo "Please run: cd frontend && npm install"
    exit 1
fi

mkdir -p "$PROJECT_ROOT/logs"

PID_FILE="$PROJECT_ROOT/logs/frontend.pid"
LOG_FILE="$PROJECT_ROOT/logs/frontend.log"

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
        echo "Frontend is already running (PID $OLD_PID)"
        echo "Run ./stop_frontend.sh to stop it first"
        exit 1
    fi
    rm -f "$PID_FILE"
fi

EXISTING_PIDS="$(get_listen_pids "$PORT")"
if [ -n "$EXISTING_PIDS" ]; then
    echo "Frontend is already listening on port $PORT: $EXISTING_PIDS"
    echo "Run ./stop_frontend.sh to stop it first"
    exit 1
fi

# Get local IP address
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo "Starting Daily Ladder Bot Frontend (background)..."
echo "====================================="
echo ""
echo "Access URLs:"
echo "  Local:      http://localhost:$PORT"
if [ -n "$LOCAL_IP" ]; then
    echo "  Network:    http://$LOCAL_IP:$PORT"
    echo "  Access from any device on your LAN using: http://$LOCAL_IP:$PORT"
fi
echo ""
echo "Backend should be running on http://localhost:8030"
echo "Logs:    $LOG_FILE"
echo "To stop: ./stop_frontend.sh"
echo ""

nohup setsid npm --prefix "$PROJECT_ROOT/frontend" run dev -- --host 0.0.0.0 --port "$PORT" >> "$LOG_FILE" 2>&1 < /dev/null &
echo $! > "$PID_FILE"

FRONTEND_PID=$(cat "$PID_FILE")
sleep 1

if ! is_pid_running "$FRONTEND_PID"; then
    echo "Frontend failed to stay running. Recent log output:"
    tail -n 50 "$LOG_FILE" 2>/dev/null || true
    rm -f "$PID_FILE"
    exit 1
fi

if ! wait_for_http "http://127.0.0.1:$PORT/" 20 1; then
    echo "Frontend process started but HTTP endpoint did not become ready. Recent log output:"
    tail -n 50 "$LOG_FILE" 2>/dev/null || true
    exit 1
fi

echo "Frontend started (PID $FRONTEND_PID)"
