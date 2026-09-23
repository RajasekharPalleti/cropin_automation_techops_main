:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
printf "\033]0;RESTART_SERVER\007"
echo "Restarting Cropin Automation Server..."
cd "$(dirname "$0")"
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
echo ========================================================
echo  Restarting Cropin Automation Server
echo ========================================================

for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
cd /d "%PROJECT_DIR%"
pushd "%PROJECT_DIR%"

:: Find configured port
for /f "tokens=2 delims==" %%I in ('findstr "SERVER_PORT" "%PROJECT_DIR%\app\script_configs.py" 2^>nul') do set PORT=%%I
set PORT=%PORT: =%
if "%PORT%"=="" set PORT=4444

:: Kill existing process on port using native findstr (avoids git find.exe collision)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo Killing existing process on port %PORT% (PID: %%a)
    taskkill /f /t /pid %%a >nul 2>&1
)
ping 127.0.0.1 -n 5 >nul

echo Starting Server
echo Open http://localhost:%PORT% or http://YOUR-IP-HERE:%PORT% in your browser.

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

:: 4. Launch Main Application
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
