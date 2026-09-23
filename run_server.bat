:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# ========================================================
# Mac/Linux execution path
# ========================================================
printf "\033]0;CROPIN_SERVER\007"
echo "Starting Cropin Automation Server..."
echo "Open http://localhost:4444 or http://<your-ip>:4444 in your browser."
cd "$(dirname "$0")"

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
echo Starting Cropin Automation Server
echo Open http://localhost:4444 or http://YOUR-IP-HERE:4444 in your browser.

for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
cd /d "%PROJECT_DIR%"
pushd "%PROJECT_DIR%"

:: 1. Verify Virtual Environment or Python availability
set PYTHON_CMD=python
set "VENV_PY=%PROJECT_DIR%\.venv\Scripts\python.exe"

if exist "%VENV_PY%" goto :VENV_FOUND

python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 goto :PYTHON_OK

py --version >nul 2>&1
if %ERRORLEVEL% EQU 0 goto :PY_OK

py -3 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 goto :PY3_OK

echo.
echo ========================================================
echo [ERROR] Python is not installed or not in your PATH!
echo Please install Python from https://www.python.org/
echo Make sure to check 'Add Python to PATH' during install.
echo ========================================================
if "%~1"=="--no-pause" goto :EXIT_ERR
if "%~2"=="--no-pause" goto :EXIT_ERR
pause
:EXIT_ERR
popd
exit /b 1

:PY_OK
set PYTHON_CMD=py
goto :PYTHON_OK

:PY3_OK
set PYTHON_CMD=py -3
goto :PYTHON_OK

:VENV_FOUND
echo Using existing virtual environment Python
goto :CHECK_VENV_ACTIVATE

:PYTHON_OK

:CHECK_VENV_ACTIVATE
:: 2. Verify Windows-compatible Virtual Environment
set DO_INSTALL=0
if exist "%PROJECT_DIR%\.venv\Scripts\activate.bat" goto :ACTIVATE_OK

echo Creating fresh virtual environment for Windows
if exist "%PROJECT_DIR%\.venv" rmdir /s /q "%PROJECT_DIR%\.venv" >nul 2>&1
%PYTHON_CMD% -m venv "%PROJECT_DIR%\.venv"
set DO_INSTALL=1

:ACTIVATE_OK
if "%~1"=="--install-deps" set DO_INSTALL=1
if "%~2"=="--install-deps" set DO_INSTALL=1

if exist "%PROJECT_DIR%\.venv\Scripts\activate.bat" goto :ACTIVATE_EXISTS

echo.
echo ========================================================
echo [ERROR] Could not find or create .venv\Scripts\activate.bat!
echo Check that Python has the venv module available.
echo ========================================================
if "%~1"=="--no-pause" goto :EXIT_ERR
if "%~2"=="--no-pause" goto :EXIT_ERR
pause
popd
exit /b 1

:ACTIVATE_EXISTS
call "%PROJECT_DIR%\.venv\Scripts\activate.bat"

:: 3. Initial dependency installation if newly created
if %DO_INSTALL% NEQ 1 goto :SKIP_INSTALL
echo Installing requirements (one-time setup)
"%PROJECT_DIR%\.venv\Scripts\python.exe" -m pip install -r requirements.txt
"%PROJECT_DIR%\.venv\Scripts\python.exe" -m playwright install chromium

:SKIP_INSTALL

:: 4. Launch Auto-Updater in background
echo Starting Auto-Updater (Runs daily at 12:00 AM)
start /b "" "%PROJECT_DIR%\.venv\Scripts\python.exe" auto_update.py >nul 2>&1

:: 5. Launch Main Application
if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" goto :RUN_VENV_APP
python -m app.main
goto :CHECK_APP_EXIT

:RUN_VENV_APP
"%PROJECT_DIR%\.venv\Scripts\python.exe" -m app.main

:CHECK_APP_EXIT
set SERVER_EXIT=%ERRORLEVEL%
popd

if %SERVER_EXIT% EQU 0 goto :SERVER_OK
echo.
echo ========================================================
echo [ERROR] Server stopped with exit code %SERVER_EXIT%!
echo If this is an error, review the error message above.
echo ========================================================
if "%~1"=="--no-pause" exit /b %SERVER_EXIT%
if "%~2"=="--no-pause" exit /b %SERVER_EXIT%
pause
exit /b %SERVER_EXIT%

:SERVER_OK
if "%~1"=="--no-pause" exit /b
if "%~2"=="--no-pause" exit /b
pause
