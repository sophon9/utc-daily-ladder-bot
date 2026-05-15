#!/bin/bash
# Run script to start BOTH EMA Trading Bot backend and frontend (background mode)

cd "$(dirname "$0")"

echo "Starting EMA Trading Bot (backend + frontend)..."
echo "==============================================="
echo ""

# Start backend
if [ -x "./run_backend.sh" ]; then
  ./run_backend.sh
else
  echo "Error: ./run_backend.sh not found or not executable"
  exit 1
fi

echo ""

# Start frontend
if [ -x "./run_frontend.sh" ]; then
  ./run_frontend.sh
else
  echo "Error: ./run_frontend.sh not found or not executable"
  exit 1
fi

echo ""
echo "✓ Backend and frontend start commands issued."
echo "  - Backend log:  logs/backend.log"
echo "  - Frontend log: logs/frontend.log"
echo ""
echo "To stop them:"
echo "  ./stop_backend.sh"
echo "  ./stop_frontend.sh"

