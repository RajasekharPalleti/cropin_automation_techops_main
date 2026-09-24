#!/bin/bash
# ========================================================
# Cropin Automation Services (Server + Ngrok) - macOS / Linux Launcher
# ========================================================

# Change directory to project root
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# Terminal window title
printf "\033]0;CROPIN_ALL_SERVICES\007" 2>/dev/null || true

echo "========================================================"
echo " Starting Cropin Automation Services (Server + Ngrok)..."
echo "========================================================"

PORT=$(grep "SERVER_PORT" app/script_configs.py 2>/dev/null | cut -d'=' -f2 | tr -d ' ' | tr -d '\r')
if [ -z "$PORT" ]; then PORT=4444; fi

LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
echo "Configured Port: $PORT"
echo "Local Access:    http://localhost:$PORT"
echo "Network Access:  http://${LOCAL_IP}:$PORT"
echo "========================================================"
echo ""

# 1. Start Server if not already running
if lsof -i :$PORT >/dev/null 2>&1 || nc -z 127.0.0.1 $PORT 2>/dev/null; then
    echo "ℹ️  Server is already running on port $PORT."
else
    echo "1. Starting Server in background..."
    bash ./run_server.sh &
    
    echo "Waiting for Server to be ready on port $PORT..."
    for i in {1..30}; do
        if lsof -i :$PORT >/dev/null 2>&1 || nc -z 127.0.0.1 $PORT 2>/dev/null; then
            echo "✅ Server is UP on port $PORT!"
            break
        fi
        sleep 1
    done
fi

# 2. Check and start Ngrok tunnel
echo ""
echo "2. Checking Ngrok Tunnel..."
if pgrep -x "ngrok" >/dev/null 2>&1; then
    echo "ℹ️  Ngrok is already running."
else
    if [ -f "./run_ngrok.sh" ]; then
        bash ./run_ngrok.sh
    elif command -v ngrok >/dev/null 2>&1; then
        echo "Starting ngrok on port $PORT..."
        ngrok http $PORT
    else
        echo "ℹ️  Ngrok is not installed on this Mac."
        echo "   Local access is ready at: http://localhost:$PORT"
        echo "   To enable remote access: brew install ngrok"
    fi
fi
