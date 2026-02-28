:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
echo "Stopping Server on port 4444..."
PID=$(lsof -ti:4444)
if [ -n "$PID" ]; then
  kill -9 $PID
  echo "Server stopped (PID: $PID)."
else
  echo "No server found running on port 4444."
fi
read -p "Press any key to close..."
exit 0

:WINDOWS
echo Stopping Server on port 4444...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":4444" ^| find "LISTENING"') do taskkill /f /pid %%a
echo Server stopped.
pause
