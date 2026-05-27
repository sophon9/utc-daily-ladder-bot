#!/bin/bash
# Stop script for Daily Ladder Bot frontend

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT=3030

kill_pid_group() {
    local pid="$1"
    if kill -0 "$pid" 2>/dev/null; then
        kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    fi
}

wait_for_pid_exit() {
    local pid="$1"
    local attempts="${2:-10}"
    local i
    for ((i = 1; i <= attempts; i++)); do
        if ! kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        sleep 1
    done
    return 1
}

echo "Stopping Daily Ladder Bot Frontend..."

# Kill by PID file if available
PID_FILE="$PROJECT_ROOT/logs/frontend.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "  Killing frontend process group (PID $PID)"
        kill_pid_group "$PID"
        if ! wait_for_pid_exit "$PID" 5; then
            echo "  Force killing PID $PID"
            kill -9 "$PID" 2>/dev/null || true
        fi
    fi
    rm -f "$PID_FILE"
fi

# Fallback: kill by port
PIDS=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$PIDS" ]; then
    echo "  Killing remaining process(es) on port $PORT: $PIDS"
    kill $PIDS 2>/dev/null || true
    sleep 2
    PIDS=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "  Force killing: $PIDS"
        kill -9 $PIDS 2>/dev/null || true
    fi
fi

echo "  Frontend stopped"
