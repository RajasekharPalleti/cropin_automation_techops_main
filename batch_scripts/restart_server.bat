:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
printf "\033]0;RESTART_SERVER\007"
echo "Restarting Cropin Automation Server..."
cd "$(dirname "$0")/.."
PORT=$(grep "SERVER_PORT" app/script_configs.py 2>/dev/null | cut -d'=' -f2 | tr -d ' ')
if [ -z "$PORT" ]; then PORT=4444; fi

PID=$(lsof -ti:$PORT 2>/dev/null)
if [ -n "$PID" ]; then
  kill -9 $PID
  echo "Old Process (PID: $PID) killed."
else
  echo "No existing process found on port $PORT."
fi
sleep 2

echo "Starting Server..."
echo "Open http://localhost:$PORT or http://<your-ip>:$PORT in your browser."
if [ ! -d ".venv" ]; then
    echo "Creating new virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip3 install -r requirements.txt
    playwright install chromium
else
    source .venv/bin/activate
fi

python3 -m app.main
read -p "Press any key to close..."
exit 0

:WINDOWS
title RESTART_SERVER
echo Restarting Cropin Automation Server...

pushd "%~dp0.."

:: Find configured port
for /f "tokens=2 delims==" %%I in ('findstr "SERVER_PORT" app\script_configs.py 2^>nul') do set PORT=%%I
set PORT=%PORT: =%
if "%PORT%"=="" set PORT=4444

:: Kill existing process on port
for /f "tokens=5" %%a in ('netstat -aon ^| find ":%PORT%" ^| find "LISTENING"') do (
    echo Killing existing process on port %PORT% (PID: %%a)...
    taskkill /f /pid %%a >nul 2>&1
)
timeout /t 2 >nul

echo Starting Server...
echo Open http://localhost:%PORT% or http://<your-ip>:%PORT% in your browser.

set DO_INSTALL=0
if not exist .venv\Scripts\activate.bat (
    echo Creating new virtual environment...
    if exist .venv rmdir /s /q .venv >nul 2>&1
    python -m venv .venv
    set DO_INSTALL=1
)

if "%~1"=="--install-deps" set DO_INSTALL=1

call .venv\Scripts\activate.bat

if %DO_INSTALL%==1 (
    echo Installing/Updating requirements...
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

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe -m app.main
) else (
    python -m app.main
)

set SERVER_EXIT=%ERRORLEVEL%
popd

if %SERVER_EXIT% NEQ 0 (
    echo.
    echo ========================================================
    echo [ERROR] Server crashed with exit code %SERVER_EXIT%!
    echo ========================================================
    pause
    exit /b %SERVER_EXIT%
)

if "%~1"=="--no-pause" exit /b
pause
