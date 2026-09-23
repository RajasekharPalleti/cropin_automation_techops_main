:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
printf "\033]0;CROPIN_ALL_SERVICES\007"
echo "========================================================"
echo " Starting Cropin Automation Services (Server + Ngrok)..."
echo "========================================================"
cd "$(dirname "$0")"

PORT=$(grep "SERVER_PORT" app/script_configs.py 2>/dev/null | cut -d'=' -f2 | tr -d ' ')
if [ -z "$PORT" ]; then PORT=4444; fi

# Check if server is already running
if nc -z 127.0.0.1 $PORT 2>/dev/null; then
    echo "ℹ️  Server is already running on port $PORT."
else
    echo "1. Starting Server..."
    bash ./run_server.bat &
    
    echo "Waiting for Server to be ready on port $PORT..."
    for i in {1..60}; do
        if nc -z 127.0.0.1 $PORT 2>/dev/null || (echo > /dev/tcp/127.0.0.1/$PORT) 2>/dev/null; then
            echo "✅ Server is UP on port $PORT!"
            break
        fi
        sleep 1
    done
fi

# Check if ngrok is already running
if pgrep -x "ngrok" >/dev/null 2>&1; then
    echo "ℹ️  Ngrok is already running."
else
    echo "2. Starting Ngrok Tunnel..."
    bash ./run_ngrok.bat
fi
exit 0

:WINDOWS
title CROPIN_ALL_SERVICES
echo ========================================================
echo  Starting Cropin Automation Services (Server + Ngrok)
echo ========================================================
echo.

:: Get canonical PROJECT_DIR
for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"

cd /d "%PROJECT_DIR%"
pushd "%PROJECT_DIR%"

:: Find configured port using absolute path
for /f "tokens=2 delims==" %%I in ('findstr "SERVER_PORT" "%PROJECT_DIR%\app\script_configs.py" 2^>nul') do set PORT=%%I
set PORT=%PORT: =%
if "%PORT%"=="" set PORT=4444

echo [INFO] Project: %PROJECT_DIR%
echo [INFO] Port:    %PORT%
echo.

:: Idempotency check: Is Server ALREADY listening on port?
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Server is already running on port %PORT%.
    goto :CHECK_NGROK
)

:: 1. Launch Server in dedicated window
::    /k keeps the window open so any crash/error stays visible
echo [1/2] Launching Server in dedicated window
start "CROPIN_SERVER" /D "%PROJECT_DIR%" cmd /k "call run_server.bat"

:: 2. Wait until Server is actually listening on the port
echo.
echo Waiting for Server to start on port %PORT% [timeout: 90s]
set RETRIES=0

:WAIT_FOR_SERVER
set /a RETRIES+=1
if %RETRIES% GTR 45 (
    echo.
    echo [WARNING] Server took longer than 90s to start. Launching Ngrok anyway.
    goto :CHECK_NGROK
)

ping 127.0.0.1 -n 3 >nul
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Server is UP and listening on port %PORT%!
    goto :CHECK_NGROK
)

<nul set /p=.
goto :WAIT_FOR_SERVER

:CHECK_NGROK
:: Check if Ngrok is already running
tasklist /FI "IMAGENAME eq ngrok.exe" 2>nul | findstr /i "ngrok.exe" >nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Ngrok tunnel is already active!
    goto :FINISH
)

:START_NGROK
echo.
echo [2/2] Launching Ngrok Remote Tunnel
start "CROPIN_NGROK" /D "%PROJECT_DIR%" cmd /k "call run_ngrok.bat"

:FINISH
echo.
echo ========================================================
echo  All services are up and active!
echo  - Server: http://localhost:%PORT%
echo  - Ngrok: See the CROPIN_NGROK window for public URL
echo ========================================================
echo.
popd

ping 127.0.0.1 -n 6 >nul
exit /b
