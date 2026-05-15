#!/bin/bash
# Stop all EMA Trading Bot services

SCRIPT_DIR="$(dirname "$0")"

echo "Stopping EMA Trading Bot (all services)..."
echo "==========================================="
echo ""

bash "$SCRIPT_DIR/stop_backend.sh"
echo ""
bash "$SCRIPT_DIR/stop_frontend.sh"

echo ""
echo "All services stopped"
