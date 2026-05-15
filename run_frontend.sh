#!/bin/bash
# Run script for EMA Trading Bot frontend (background mode)

cd "$(dirname "$0")"

# Check if node_modules exists
if [ ! -d "frontend/node_modules" ]; then
    echo "Error: node_modules not found!"
    echo "Please run: cd frontend && npm install"
    exit 1
fi

mkdir -p logs

PID_FILE="logs/frontend.pid"
LOG_FILE="logs/frontend.log"

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

echo "Starting EMA Trading Bot Frontend (background)..."
echo "====================================="
echo ""
echo "Access URLs:"
echo "  Local:      http://localhost:3010"
if [ -n "$LOCAL_IP" ]; then
    echo "  Network:    http://$LOCAL_IP:3010"
    echo "  Access from any device on your LAN using: http://$LOCAL_IP:3010"
fi
echo ""
echo "Backend should be running on http://localhost:8010"
echo "Logs:    $LOG_FILE"
echo "To stop: ./stop_frontend.sh"
echo ""

cd frontend
nohup npm run dev >> "../$LOG_FILE" 2>&1 &
echo $! > "../$PID_FILE"

echo "Frontend started (PID $(cat ../$PID_FILE))"
