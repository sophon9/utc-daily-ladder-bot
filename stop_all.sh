#!/bin/bash
# Stop all Daily Ladder Bot services

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Stopping Daily Ladder Bot (all services)..."
echo "==========================================="
echo ""

bash "$SCRIPT_DIR/stop_backend.sh"
echo ""
bash "$SCRIPT_DIR/stop_frontend.sh"

echo ""
echo "All services stopped"
