:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
printf "\033]0;STOP_SERVER\007"
cd "$(dirname "$0")"
PORT=$(grep "SERVER_PORT" app/script_configs.py 2>/dev/null | cut -d'=' -f2 | tr -d ' ')
if [ -z "$PORT" ]; then PORT=4444; fi

echo "Stopping Server on port $PORT..."
PID=$(lsof -ti:$PORT 2>/dev/null)
if [ -n "$PID" ]; then
  kill -9 $PID
  echo "Server stopped (PID: $PID)."
else
  echo "No server found running on port $PORT."
fi
read -p "Press any key to close..."
exit 0

:WINDOWS
title STOP_SERVER
for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
cd /d "%PROJECT_DIR%"
pushd "%PROJECT_DIR%"

:: Find configured port
for /f "tokens=2 delims==" %%I in ('findstr "SERVER_PORT" "%PROJECT_DIR%\app\script_configs.py" 2^>nul') do set PORT=%%I
set PORT=%PORT: =%
if "%PORT%"=="" set PORT=4444

echo Stopping Server on port %PORT%
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo Killing process PID %%a listening on port %PORT%
    taskkill /f /t /pid %%a >nul 2>&1
)
echo Server stopped.
popd

if "%~1"=="--no-pause" exit /b
pause
