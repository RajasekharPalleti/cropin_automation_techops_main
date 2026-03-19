#!/bin/bash

# Default to port 4444 if PORT is not set
echo -ne "\033]0;RAILWAY_SERVER\007"
PORT="${PORT:-4444}"

echo "Starting app on port $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
