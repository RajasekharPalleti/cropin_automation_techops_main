:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
echo "Stopping all ghost ngrok processes..."
pkill -9 ngrok || true
echo "Stopped existing ngrok processes."
read -p "Press any key to close..."
exit 0

:WINDOWS
@echo off
echo Stopping all ghost ngrok processes...
taskkill /IM ngrok.exe /F
if %ERRORLEVEL% EQU 0 (
    echo.
    echo Successfully killed ngrok.
) else (
    echo.
    echo No ngrok process was running, or failed to kill.
)
pause
