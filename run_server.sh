#!/bin/bash
# ========================================================
# Cropin Automation Server - macOS / Linux Launcher
# ========================================================
set -e

# Change directory to project root
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# Terminal window title
printf "\033]0;CROPIN_SERVER\007" 2>/dev/null || true

echo "========================================================"
echo " Starting Cropin Automation Server..."
echo "========================================================"

# Read configured port from app/script_configs.py or default to 4444
PORT=$(grep "SERVER_PORT" app/script_configs.py 2>/dev/null | cut -d'=' -f2 | tr -d ' ' | tr -d '\r')
if [ -z "$PORT" ]; then PORT=4444; fi

LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
echo "Configured Port: $PORT"
echo "Local Access:    http://localhost:$PORT"
echo "Network Access:  http://${LOCAL_IP}:$PORT"
echo "========================================================"
echo ""

# Find Python 3
if command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PY_CMD="python"
else
    echo "❌ [ERROR] Python 3 is not installed or not in your PATH."
    echo "Please install Python from https://www.python.org/ or via 'brew install python'"
    exit 1
fi

# Virtual Environment Setup
DO_INSTALL=0
if [ -d ".venv" ] && [ ! -f ".venv/bin/activate" ]; then
    echo "⚠️  Detected incompatible/Windows virtual environment. Re-creating for macOS..."
    rm -rf .venv
fi

if [ ! -f ".venv/bin/activate" ]; then
    echo "Creating new virtual environment (.venv)..."
    "$PY_CMD" -m venv .venv
    DO_INSTALL=1
fi

echo "Activating virtual environment..."
source .venv/bin/activate

# Dependency installation if requested or newly created
if [ "$1" = "--install-deps" ] || [ "$2" = "--install-deps" ] || [ "$DO_INSTALL" -eq 1 ]; then
    echo "Installing / Updating dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
    playwright install chromium 2>/dev/null || true
fi

# Check if port is already running
EXISTING_PID=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$EXISTING_PID" ]; then
    echo "ℹ️  Port $PORT is already in use by PID $EXISTING_PID."
    if [ "$1" = "--force" ] || [ "$1" = "-f" ] || [ "$2" = "--force" ]; then
        echo "Stopping existing process on port $PORT..."
        kill -9 $EXISTING_PID 2>/dev/null || true
        sleep 1
    else
        echo "To stop the existing server, run: ./stop_server.sh"
        echo "Or pass --force to restart: ./run_server.sh --force"
    fi
fi

# Start auto-updater in background if present
if [ -f "auto_update.py" ]; then
    echo "Starting Auto-Updater in background (daily at 12:00 AM)..."
    nohup python3 auto_update.py >/dev/null 2>&1 &
fi

echo "Starting Cropin Automation Server on http://localhost:$PORT ..."
python3 -m app.main
