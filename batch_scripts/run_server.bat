:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
printf "\033]0;CROPIN_SERVER\007"
echo "Starting Cropin Automation Server..."
echo "Open http://localhost:4444 or http://<your-ip>:4444 in your browser."
cd "$(dirname "$0")/.."

echo "Activating virtual environment..."
DO_INSTALL=0
if [ ! -f ".venv/bin/activate" ]; then
    echo "Creating new virtual environment..."
    rm -rf .venv 2>/dev/null
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
nohup python3 auto_update.py >/dev/null 2>&1 &

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
echo Open http://localhost:4444 or http://YOUR-IP-HERE:4444 in your browser.
pushd "%~dp0.."

:: 1. Verify Python availability
set PYTHON_CMD=python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    py --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set PYTHON_CMD=py
    ) else (
        echo.
        echo ========================================================
        echo [ERROR] Python is not installed or not in your PATH!
        echo Please install Python from https://www.python.org/
        echo Make sure to check 'Add Python to PATH' during install.
        echo ========================================================
        pause
        popd
        exit /b 1
    )
)

:: 2. Verify Windows-compatible Virtual Environment
set DO_INSTALL=0
if not exist .venv\Scripts\activate.bat (
    echo Creating fresh virtual environment for Windows...
    if exist .venv rmdir /s /q .venv >nul 2>&1
    %PYTHON_CMD% -m venv .venv
    set DO_INSTALL=1
)

if "%~1"=="--install-deps" set DO_INSTALL=1
if "%~2"=="--install-deps" set DO_INSTALL=1

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    echo.
    echo [ERROR] Could not find .venv\Scripts\activate.bat!
    pause
    popd
    exit /b 1
)

:: 3. Initial dependency installation if newly created
if %DO_INSTALL%==1 (
    echo Installing requirements (one-time setup)...
    python -m pip install -r requirements.txt
    python -m playwright install chromium
)

:: 4. Launch Auto-Updater in background
echo Starting Auto-Updater (Runs daily at 12:00 AM)...
start /b python auto_update.py >nul 2>&1

:: 5. Launch Main Application
python -m app.main
set SERVER_EXIT=%ERRORLEVEL%
popd

if %SERVER_EXIT% NEQ 0 (
    echo.
    echo ========================================================
    echo [ERROR] Server stopped with exit code %SERVER_EXIT%!
    echo If this is an error, review the error message above.
    echo ========================================================
    pause
    exit /b %SERVER_EXIT%
)

if "%~1"=="--no-pause" exit /b
if "%~2"=="--no-pause" exit /b
pause
