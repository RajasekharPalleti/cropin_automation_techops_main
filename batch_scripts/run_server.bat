:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
echo -ne "\033]0;CROPIN_SERVER\007"
echo "Starting Cropin Automation Server..."
echo "Open http://localhost:4444 or http://<your-ip>:4444 in your browser."
cd "$(dirname "$0")/.."

echo "Activating virtual environment..."
if [ ! -d ".venv" ]; then
    echo "Creating new virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "Starting Auto-Updater (Runs daily at 12:00 AM)..."
nohup python3 auto_update.py >/dev/null 2>&1 &

echo "Installing/Updating requirements..."
pip3 install -r requirements.txt
python3 -m app.main
read -p "Press any key to close..."
exit 0

:WINDOWS
title CROPIN_SERVER
echo Starting Cropin Automation Server...
echo Open http://localhost:4444 or http://<your-ip>:4444 in your browser.
pushd %~dp0\..\

echo Starting Auto-Updater (Runs daily at 12:00 AM)...
start /b python auto_update.py >nul 2>&1

echo Installing/Updating requirements...
pip install -r requirements.txt
python -m app.main
popd
pause
