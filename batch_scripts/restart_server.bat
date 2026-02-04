:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
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
python3 -m app.main
read -p "Press any key to close..."
exit 0

:WINDOWS
echo Restarting Cropin Automation Server...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":4444" ^| find "LISTENING"') do taskkill /f /pid %%a
timeout /t 2 >nul
echo Starting Server...
echo Open http://localhost:4444 or http://<your-ip>:4444 in your browser.
pushd %~dp0\..\
python -m app.main
popd
pause
