@echo off
REM Cropin Automation - Launcher Startup Script (Windows)
REM
REM Double-click this file on the friend's machine to start the launcher.
REM The launcher (port 4445) starts the main app (port 4444) on demand
REM when the website button is clicked.

setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "LAUNCHER_PORT=4445"
if defined LAUNCHER_PORT_OVERRIDE set "LAUNCHER_PORT=%LAUNCHER_PORT_OVERRIDE%"

echo [launcher] Checking dependencies...
python -c "import fastapi, uvicorn" 2>nul
if errorlevel 1 (
    echo [launcher] Installing dependencies...
    python -m pip install -r requirements.txt --quiet
)

echo [launcher] Stopping any previous launcher on port %LAUNCHER_PORT%...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%LAUNCHER_PORT% " 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo [launcher] Starting Cropin Automation Launcher on port %LAUNCHER_PORT%...
echo [launcher] Close this window to stop the launcher.
echo.

python launcher.py

pause
