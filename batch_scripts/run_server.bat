:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
echo -ne "\033]0;CROPIN_SERVER\007"
echo "Starting Cropin Automation Server..."
echo "Open http://localhost:4444 or http://<your-ip>:4444 in your browser."
cd "$(dirname "$0")/.."

echo "Activating virtual environment..."
DO_INSTALL=0
if [ ! -d ".venv" ]; then
    echo "Creating new virtual environment..."
    python3 -m venv .venv
    DO_INSTALL=1
fi
source .venv/bin/activate

if [ "$1" == "--install-deps" ] || [ "$2" == "--install-deps" ] || [ $DO_INSTALL -eq 1 ]; then
    echo "Installing/Updating requirements..."
    pip3 install -r requirements.txt
    playwright install chromium
fi

echo "Starting Auto-Updater (Runs daily at 12:00 AM)..."
nohup python3 auto_update.py >> server.log 2>&1 &

python3 -m app.main
SERVER_EXIT=$?
if [ $SERVER_EXIT -ne 0 ]; then
    echo ""
    echo "========================================================"
    echo "[ERROR] Server crashed with exit code $SERVER_EXIT!"
    echo "Check the error traceback above or check server.log."
    echo "========================================================"
    read -p "Press any key to close..."
fi
exit $SERVER_EXIT

:WINDOWS
title CROPIN_SERVER
echo Starting Cropin Automation Server...
echo Open http://localhost:4444 or http://<your-ip>:4444 in your browser.
pushd %~dp0\..\

set DO_INSTALL=0
if not exist .venv (
    echo Creating new virtual environment...
    python -m venv .venv
    set DO_INSTALL=1
)

if "%~1"=="--install-deps" set DO_INSTALL=1
if "%~2"=="--install-deps" set DO_INSTALL=1

call .venv\Scripts\activate

if %DO_INSTALL%==1 (
    echo Installing/Updating requirements (Initial setup)...
    if exist .venv\Scripts\pip.exe (
        .venv\Scripts\pip.exe install -r requirements.txt
    ) else (
        pip install -r requirements.txt
    )
    if exist .venv\Scripts\playwright.exe (
        .venv\Scripts\playwright.exe install chromium
    ) else (
        playwright install chromium
    )
)

echo Starting Auto-Updater (Runs daily at 12:00 AM)...
if exist .venv\Scripts\python.exe (
    start /b "" .venv\Scripts\python.exe auto_update.py >> server.log 2>&1
    .venv\Scripts\python.exe -m app.main
) else (
    start /b "" python auto_update.py >> server.log 2>&1
    python -m app.main
)

set SERVER_EXIT=%ERRORLEVEL%
popd

if %SERVER_EXIT% NEQ 0 (
    echo.
    echo ========================================================
    echo [ERROR] Server crashed with exit code %SERVER_EXIT%!
    echo Check the error traceback above or check server.log.
    echo ========================================================
    pause
    exit /b %SERVER_EXIT%
)

if "%~1"=="--no-pause" exit /b
if "%~2"=="--no-pause" exit /b
pause
