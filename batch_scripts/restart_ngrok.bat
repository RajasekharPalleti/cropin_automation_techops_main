:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
echo -ne "\033]0;RESTART_NGROK\007"
echo "Restarting ngrok..."
pkill -9 ngrok || true
echo "Stopped existing ngrok processes."
echo "Starting new tunnel..."
echo "The public URL will appear below."
cd "$(dirname "$0")/.."
ngrok http 4444
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
pushd %~dp0\..\
ngrok http 4444
popd
pause
