:; exec "$(dirname "$0")/stop_server.sh" "$@"
@echo off
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
