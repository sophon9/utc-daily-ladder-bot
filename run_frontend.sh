#!/bin/bash
# Run script for Daily Ladder Bot frontend (background mode)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Check if node_modules exists
if [ ! -d "$PROJECT_ROOT/frontend/node_modules" ]; then
    echo "Error: node_modules not found!"
    echo "Please run: cd frontend && npm install"
    exit 1
fi

mkdir -p "$PROJECT_ROOT/logs"

PID_FILE="$PROJECT_ROOT/logs/frontend.pid"
LOG_FILE="$PROJECT_ROOT/logs/frontend.log"

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Frontend is already running (PID $OLD_PID)"
        echo "Run ./stop_frontend.sh to stop it first"
        exit 1
    fi
    rm -f "$PID_FILE"
fi

# Get local IP address
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo "Starting Daily Ladder Bot Frontend (background)..."
echo "====================================="
echo ""
echo "Access URLs:"
echo "  Local:      http://localhost:3030"
if [ -n "$LOCAL_IP" ]; then
    echo "  Network:    http://$LOCAL_IP:3030"
    echo "  Access from any device on your LAN using: http://$LOCAL_IP:3030"
fi
echo ""
echo "Backend should be running on http://localhost:8030"
echo "Logs:    $LOG_FILE"
echo "To stop: ./stop_frontend.sh"
echo ""

nohup setsid npm --prefix "$PROJECT_ROOT/frontend" run dev -- --host 0.0.0.0 --port 3030 >> "$LOG_FILE" 2>&1 < /dev/null &
echo $! > "$PID_FILE"

FRONTEND_PID=$(cat "$PID_FILE")
sleep 3

if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "Frontend failed to stay running. Recent log output:"
    tail -n 50 "$LOG_FILE" 2>/dev/null || true
    rm -f "$PID_FILE"
    exit 1
fi

if ! curl -fsS "http://127.0.0.1:3030/" >/dev/null 2>&1; then
    echo "Frontend process started but HTTP endpoint did not become ready. Recent log output:"
    tail -n 50 "$LOG_FILE" 2>/dev/null || true
    exit 1
fi

echo "Frontend started (PID $FRONTEND_PID)"
