#!/bin/bash
# Setup script for EMA Trading Bot

cd "$(dirname "$0")"

VENV_DIR="$HOME/.venvs/ema_bot"

echo "========================================="
echo "  EMA Trading Bot - Setup Script"
echo "========================================="
echo ""

# Check Python version
echo "[1/7] Checking Python version..."
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
if (( $(echo "$python_version >= 3.11" | bc -l) )); then
    echo "✓ Python $python_version found"
else
    echo "✗ Python 3.11+ required (found $python_version)"
    exit 1
fi
echo ""

# Check Node.js
echo "[2/7] Checking Node.js..."
if command -v node &> /dev/null; then
    node_version=$(node --version)
    echo "✓ Node.js $node_version found"
else
    echo "✗ Node.js not found. Please install Node.js 18+"
    exit 1
fi
echo ""

# Setup backend
echo "[3/7] Setting up Python virtual environment..."
mkdir -p "$(dirname "$VENV_DIR")"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

echo ""
echo "[4/7] Installing Python dependencies..."
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r backend/requirements.txt
echo "✓ Python dependencies installed"
echo ""

# Setup frontend
echo "[5/7] Installing frontend dependencies..."
cd frontend
if [ ! -d "node_modules" ]; then
    npm install
    echo "✓ Frontend dependencies installed"
else
    echo "✓ Frontend dependencies already installed"
fi
cd ..
echo ""

# Setup config files
echo "[6/7] Setting up configuration files..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✓ Created .env (please edit with your API credentials)"
else
    echo "✓ .env already exists"
fi

if [ ! -f "config.json" ]; then
    cp config.example.json config.json
    echo "✓ Created config.json"
else
    echo "✓ config.json already exists"
fi
echo ""

# Create directories
echo "[7/7] Creating required directories..."
mkdir -p logs data
echo "✓ Created logs/ and data/ directories"
echo ""

# Done
echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Edit .env with your Bybit API credentials:"
echo "   nano .env"
echo ""
echo "2. Review and adjust config.json:"
echo "   nano config.json"
echo ""
echo "3. Run smoke test (optional but recommended):"
echo "   source $VENV_DIR/bin/activate"
echo "   python scripts/smoke_test.py"
echo ""
echo "4. Start the backend (Terminal 1):"
echo "   ./run_backend.sh"
echo ""
echo "5. Start the frontend (Terminal 2):"
echo "   ./run_frontend.sh"
echo ""
echo "6. Open browser to http://localhost:3010"
echo ""
echo "⚠️  IMPORTANT: Start with testnet and dry_run mode!"
echo ""
