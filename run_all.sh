#!/bin/bash
# Run script to start BOTH Daily Ladder Bot backend and frontend

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

echo "Starting Daily Ladder Bot (backend + frontend)..."
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
  if ! ./run_frontend.sh; then
    echo ""
    echo "Frontend failed to start. Stopping backend to avoid a partial launch."
    ./stop_backend.sh || true
    exit 1
  fi
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
