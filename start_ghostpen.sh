#!/usr/bin/env bash
# ============================================================
# GhostPen: One-Click Startup Script for macOS & Linux
# ============================================================
set -e

# Resolve repository directory using strictly relative path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  GhostPen: Writing-Style Verification for BEC Defense"
echo "============================================================"
echo ""

# 1. Detect Python executable
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python was not found on your system."
    echo ""
    echo "GhostPen requires Python 3.10 or newer."
    echo "Installation instructions:"
    echo "  - macOS: brew install python"
    echo "  - Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-venv python3-pip"
    echo "  - Fedora: sudo dnf install python3 python3-pip"
    echo "  - Or download from: https://www.python.org/downloads/"
    exit 1
fi

PY_VER=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
echo "[INFO] Found Python $PY_VER ($PYTHON_CMD)"

# 2. Setup or activate virtual environment (.venv)
if [ ! -f ".venv/bin/activate" ]; then
    echo "[SETUP] Creating isolated virtual environment in .venv..."
    $PYTHON_CMD -m venv .venv || {
        echo "[ERROR] Failed to create virtual environment."
        echo "On Ubuntu/Debian, install the venv package: sudo apt install python3-venv"
        exit 1
    }
    echo "[SETUP] Virtual environment created."
fi

# Activate virtual environment
source .venv/bin/activate

# 3. Install or update dependencies
echo "[SETUP] Verifying Python dependencies from requirements.txt..."
python -m pip install -r requirements.txt --disable-pip-version-check

# 4. Run pre-flight readiness check
echo ""
echo "[CHECK] Running pre-flight system check..."
python scripts/check_ready.py

# 5. Launch Streamlit dashboard
echo ""
echo "============================================================"
echo "  Launching GhostPen Interactive Dashboard"
echo "============================================================"
echo "[INFO] Opening http://localhost:8501 in your default browser..."
echo "[INFO] To STOP the dashboard at any time, press Ctrl+C."
echo ""

exec python -m streamlit run app/app.py