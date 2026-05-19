:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
echo -ne "\033]0;CROPIN_NGROK\007"
echo "Initializing Remote Tunnel..."
echo ""
echo "The public URL will appear below."
echo "Keep this window OPEN to maintain remote access."
echo ""
cd "$(dirname "$0")/.."
ngrok http 4444
read -p "Press any key to close..."
exit 0

:WINDOWS
@echo off
title CROPIN_NGROK
echo Initializing Remote Tunnel...
echo.
echo The public URL will appear below.
echo Keep this window OPEN to maintain remote access.
echo.
pushd %~dp0\..\
ngrok http 4444
popd
if "%~1"=="--no-pause" exit /b
pause
