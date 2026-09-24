#!/bin/bash
# ========================================================
# Restart Cropin Automation Server - macOS / Linux
# ========================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"
echo "Restarting Cropin Automation Server..."
bash ./stop_server.sh
sleep 1
bash ./run_server.sh "$@"
