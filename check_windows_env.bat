@echo off
title Cropin Automation - Windows Environment Diagnostic
echo ========================================================
echo   Cropin Automation - Windows Environment Diagnostic
echo ========================================================
echo.

for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
echo [1] Checking Project Directory...
echo     Project Root: %PROJECT_DIR%
echo.

echo [2] Checking System Python...
python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo     [OK] python: %%v
) else (
    echo     [WARN] 'python' is not in PATH.
)

py --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f "tokens=*" %%v in ('py --version 2^>^&1') do echo     [OK] py launcher: %%v
) else (
    echo     [INFO] 'py' launcher not found.
)
echo.

echo [3] Checking Virtual Environment (.venv)...
if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" (
    for /f "tokens=*" %%v in ('"%PROJECT_DIR%\.venv\Scripts\python.exe" --version 2^>^&1') do (
        echo     [OK] Virtual Environment Python: %%v
    )
) else (
    echo     [WARN] .venv\Scripts\python.exe does not exist yet.
    echo            It will be created automatically on first run of run_server.bat.
)
echo.

echo [4] Checking Critical Dependencies...
if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" (
    "%PROJECT_DIR%\.venv\Scripts\python.exe" -c "import fastapi, uvicorn, playwright; print('    [OK] fastapi, uvicorn, playwright are all installed!')" 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo     [WARN] Some dependencies are missing in .venv.
        echo            Run: run_server.bat --install-deps
    )
) else (
    echo     [INFO] Skipped (virtual environment not created yet).
)
echo.

echo [5] Checking Ngrok...
if exist "%PROJECT_DIR%\ngrok.exe" (
    echo     [OK] ngrok.exe found in project root.
) else (
    ngrok --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo     [OK] ngrok found in system PATH.
    ) else (
        echo     [WARN] ngrok.exe not found in project root or system PATH.
    )
)
echo.

echo [6] Checking Port 4444 Status...
netstat -ano | findstr ":4444" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo     [INFO] Port 4444 is currently IN USE (Server is already running).
) else (
    echo     [OK] Port 4444 is FREE and ready for the server.
)
echo.

echo ========================================================
echo   Diagnostic Complete!
echo ========================================================
echo.
pause
