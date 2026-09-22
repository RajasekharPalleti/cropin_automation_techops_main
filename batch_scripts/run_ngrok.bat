:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
printf "\033]0;CROPIN_NGROK\007"
echo "Initializing Remote Tunnel..."
echo ""
echo "The public URL will appear below."
echo "Keep this window OPEN to maintain remote access."
echo ""
cd "$(dirname "$0")/.."
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
@echo off
title CROPIN_NGROK
echo Initializing Remote Tunnel...
echo.
echo The public URL will appear below.
echo Keep this window OPEN to maintain remote access.
echo.
pushd "%~dp0.."
for /f "tokens=2 delims==" %%I in ('findstr "SERVER_PORT" app\script_configs.py 2^>nul') do set PORT=%%I
set PORT=%PORT: =%
if "%PORT%"=="" set PORT=4444

set NGROK_ATTEMPTS=0

:LAUNCH_NGROK
set /a NGROK_ATTEMPTS+=1

:: Prioritize local ngrok.exe in the repository root
if exist ngrok.exe (
    ngrok.exe http %PORT%
) else if exist "%~dp0..\ngrok.exe" (
    "%~dp0..\ngrok.exe" http %PORT%
) else (
    ngrok http %PORT%
)

set NGROK_EXIT=%ERRORLEVEL%

:: If ngrok exited with error, retry up to 3 times with a delay (handles slow bootup network connections)
if %NGROK_EXIT% NEQ 0 (
    if %NGROK_ATTEMPTS% LSS 3 (
        echo.
        echo [WARNING] Ngrok exited (code %NGROK_EXIT%). Network might still be connecting.
        echo Retrying in 5 seconds (attempt %NGROK_ATTEMPTS%/3)...
        timeout /t 5 >nul
        goto :LAUNCH_NGROK
    )
)

popd

if %NGROK_EXIT% NEQ 0 (
    echo.
    echo ========================================================
    echo [ERROR] ngrok exited with code %NGROK_EXIT%!
    echo Ensure ngrok.exe exists in the project root or in system PATH.
    echo Also ensure your authtoken is configured:
    echo   ngrok config add-authtoken ^<YOUR_TOKEN^>
    echo ========================================================
    pause
    exit /b %NGROK_EXIT%
)

if "%~1"=="--no-pause" exit /b
pause
