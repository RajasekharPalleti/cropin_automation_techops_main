#!/bin/bash
# ========================================================
# Cropin Ngrok Tunnel - macOS / Linux Launcher
# ========================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"
printf "\033]0;CROPIN_NGROK\007" 2>/dev/null || true

PORT=$(grep "SERVER_PORT" app/script_configs.py 2>/dev/null | cut -d'=' -f2 | tr -d ' ' | tr -d '\r')
if [ -z "$PORT" ]; then PORT=4444; fi

echo "========================================================"
echo " Initializing Remote Tunnel for Port $PORT..."
echo " The public URL will appear below."
echo " Keep this window OPEN to maintain remote access."
echo "========================================================"
echo ""

if [ -f "./ngrok" ] && [ -x "./ngrok" ]; then
    ./ngrok http $PORT
elif command -v ngrok >/dev/null 2>&1; then
    ngrok http $PORT
else
    echo "❌ [ERROR] ngrok is not found on your system."
    echo "To install ngrok on macOS, run:"
    echo "   brew install ngrok"
    echo "Then connect your authtoken:"
    echo "   ngrok config add-authtoken <your-token>"
    echo ""
    echo "Local server is accessible at: http://localhost:$PORT"
    exit 1
fi
