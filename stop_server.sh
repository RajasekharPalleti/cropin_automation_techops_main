#!/bin/bash
# ========================================================
# Stop Cropin Automation Server - macOS / Linux
# ========================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"
PORT=$(grep "SERVER_PORT" app/script_configs.py 2>/dev/null | cut -d'=' -f2 | tr -d ' ' | tr -d '\r')
if [ -z "$PORT" ]; then PORT=4444; fi

echo "Stopping Server on port $PORT..."
PIDS=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$PIDS" ]; then
    for pid in $PIDS; do
        kill -9 $pid 2>/dev/null || true
        echo "✅ Stopped process (PID: $pid)"
    done
    echo "Server on port $PORT stopped."
else
    echo "ℹ️  No server process found running on port $PORT."
fi
