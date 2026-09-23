@echo off
title Cropin Automation - Windows Environment Diagnostic
echo ========================================================
echo   Cropin Automation - Windows Environment Diagnostic
echo ========================================================
echo.

for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
echo [1] Checking Project Directory
echo     Project Root: %PROJECT_DIR%
echo.

echo [2] Checking System Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 goto :NO_SYS_PYTHON
for /f "tokens=1,2,*" %%a in ('python --version 2^>^&1') do echo     [OK] python: %%a %%b
goto :CHECK_PY_LAUNCHER

:NO_SYS_PYTHON
echo     [WARN] 'python' is not in PATH.

:CHECK_PY_LAUNCHER
py --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 goto :NO_PY_LAUNCHER
for /f "tokens=1,2,*" %%a in ('py --version 2^>^&1') do echo     [OK] py launcher: %%a %%b
goto :AFTER_SYS_PYTHON

:NO_PY_LAUNCHER
echo     [INFO] 'py' launcher not found.

:AFTER_SYS_PYTHON
echo.

echo [3] Checking Virtual Environment (.venv)
set "VENV_PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" goto :NO_VENV
echo     [OK] Virtual Environment Python found:
"%VENV_PYTHON%" --version
goto :AFTER_VENV

:NO_VENV
echo     [WARN] .venv\Scripts\python.exe does not exist yet.
echo            It will be created automatically on first run of run_server.bat.

:AFTER_VENV
echo.

echo [4] Checking Critical Dependencies
if not exist "%VENV_PYTHON%" goto :SKIP_DEPS
"%VENV_PYTHON%" -c "import fastapi, uvicorn, playwright" >nul 2>&1
if %ERRORLEVEL% NEQ 0 goto :DEPS_MISSING
echo     [OK] fastapi, uvicorn, playwright are all installed!
goto :AFTER_DEPS

:DEPS_MISSING
echo     [WARN] Some dependencies are missing in .venv.
echo            Run: run_server.bat --install-deps
goto :AFTER_DEPS

:SKIP_DEPS
echo     [INFO] Skipped (virtual environment not created yet).

:AFTER_DEPS
echo.

echo [5] Checking Ngrok
if exist "%PROJECT_DIR%\ngrok.exe" goto :NGROK_LOCAL
ngrok --version >nul 2>&1
if %ERRORLEVEL% EQU 0 goto :NGROK_PATH
echo     [WARN] ngrok.exe not found in project root or system PATH.
goto :AFTER_NGROK

:NGROK_LOCAL
echo     [OK] ngrok.exe found in project root.
goto :AFTER_NGROK

:NGROK_PATH
echo     [OK] ngrok found in system PATH.

:AFTER_NGROK
echo.

echo [6] Checking Port 4444 Status
netstat -ano | findstr ":4444" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% NEQ 0 goto :PORT_FREE
echo     [INFO] Port 4444 is currently IN USE (Server is already running).
goto :AFTER_PORT

:PORT_FREE
echo     [OK] Port 4444 is FREE and ready for the server.

:AFTER_PORT
echo.

echo ========================================================
echo   Diagnostic Complete!
echo ========================================================
echo.
if "%~1"=="--no-pause" goto :EOF
pause
