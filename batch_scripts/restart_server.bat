:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
echo -ne "\033]0;RESTART_SERVER\007"
echo "Restarting Cropin Automation Server..."
PID=$(lsof -ti:4444)
if [ -n "$PID" ]; then
  kill -9 $PID
  echo "Old Process (PID: $PID) killed."
else
  echo "No existing process found on port 4444."
fi
sleep 2
echo "Starting Server..."
echo "Open http://localhost:4444 or http://<your-ip>:4444 in your browser."
cd "$(dirname "$0")/.."
echo "Activating virtual environment..."
if [ ! -d ".venv" ]; then
    echo "Creating new virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "Installing/Updating requirements..."
pip3 install -r requirements.txt
python3 -m app.main
read -p "Press any key to close..."
exit 0

:WINDOWS
title RESTART_SERVER
echo Restarting Cropin Automation Server...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":4444" ^| find "LISTENING"') do taskkill /f /pid %%a
timeout /t 2 >nul
echo Starting Server...
echo Open http://localhost:4444 or http://<your-ip>:4444 in your browser.
pushd %~dp0\..\
echo Installing/Updating requirements...
pip install -r requirements.txt
python -m app.main
popd
if "%~1"=="--no-pause" exit /b
pause
