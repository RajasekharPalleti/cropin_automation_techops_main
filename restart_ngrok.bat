:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
printf "\033]0;RESTART_NGROK\007"
echo "Restarting ngrok..."
pkill -9 ngrok || true
echo "Stopped existing ngrok processes."
echo "Starting new tunnel..."
echo "The public URL will appear below."
cd "$(dirname "$0")"
PORT=$(grep "SERVER_PORT" app/script_configs.py 2>/dev/null | cut -d'=' -f2 | tr -d ' ')
if [ -z "$PORT" ]; then PORT=4444; fi
if [ -f "./ngrok" ]; then
    ./ngrok http $PORT
else
    ngrok http $PORT
fi
read -p "Press any key to close..."
exit 0

:WINDOWS
title RESTART_NGROK
echo Restarting ngrok...
taskkill /IM ngrok.exe /F >nul 2>&1
echo Stopped existing ngrok processes.
echo.
echo Initializing Remote Tunnel...
echo.
echo The public URL will appear below.
echo Keep this window OPEN to maintain remote access.
echo.

for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
cd /d "%PROJECT_DIR%"
pushd "%PROJECT_DIR%"

for /f "tokens=2 delims==" %%I in ('findstr "SERVER_PORT" "%PROJECT_DIR%\app\script_configs.py" 2^>nul') do set PORT=%%I
set PORT=%PORT: =%
if "%PORT%"=="" set PORT=4444

if exist "%PROJECT_DIR%\ngrok.exe" (
    "%PROJECT_DIR%\ngrok.exe" http %PORT%
) else (
    ngrok http %PORT%
)

popd
if "%~1"=="--no-pause" exit /b
pause
