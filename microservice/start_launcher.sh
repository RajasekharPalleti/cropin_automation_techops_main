#!/usr/bin/env bash
# Cropin Automation – Launcher Startup Script (Linux / macOS)
#
# Run once on the friend's machine to keep the launcher alive.
# The launcher (port 4445) is lightweight and starts the main app
# (port 4444) on demand when the website button is clicked.
#
# Usage:
#   chmod +x start_launcher.sh
#   ./start_launcher.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------- Install launcher dependencies if needed ----------
if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "[launcher] Installing dependencies..."
    python3 -m pip install -r requirements.txt --quiet
fi

# ---------- Kill any previous launcher instance ----------
LAUNCHER_PORT="${LAUNCHER_PORT:-4445}"
existing=$(lsof -ti tcp:"$LAUNCHER_PORT" 2>/dev/null || true)
if [ -n "$existing" ]; then
    echo "[launcher] Stopping previous launcher on port $LAUNCHER_PORT..."
    kill "$existing" 2>/dev/null || true
    sleep 1
fi

echo "[launcher] Starting Cropin Automation Launcher on port $LAUNCHER_PORT..."
echo "[launcher] Press Ctrl+C to stop."
echo ""

python3 launcher.py
