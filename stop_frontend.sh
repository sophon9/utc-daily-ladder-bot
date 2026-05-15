#!/bin/bash
# Stop script for Daily Ladder Bot frontend

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Stopping Daily Ladder Bot Frontend..."

# Kill by PID file if available
PID_FILE="$PROJECT_ROOT/logs/frontend.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "  Killing frontend process (PID $PID)"
        kill "$PID" 2>/dev/null
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            echo "  Force killing PID $PID"
            kill -9 "$PID" 2>/dev/null
        fi
    fi
    rm -f "$PID_FILE"
fi

# Fallback: kill by port
PIDS=$(lsof -ti :3010 2>/dev/null)
if [ -n "$PIDS" ]; then
    echo "  Killing remaining process(es) on port 3010: $PIDS"
    kill $PIDS 2>/dev/null
    sleep 2
    PIDS=$(lsof -ti :3010 2>/dev/null)
    if [ -n "$PIDS" ]; then
        echo "  Force killing: $PIDS"
        kill -9 $PIDS 2>/dev/null
    fi
fi

echo "  Frontend stopped"
