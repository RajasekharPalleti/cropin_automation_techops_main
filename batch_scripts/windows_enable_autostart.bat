@echo off
title Cropin Server Auto-Start Setup
echo ========================================================
echo  Cropin Server - Windows Auto-Start Setup
echo ========================================================
echo.
echo This script configures the server machine to automatically
echo start both the Cropin Automation Server and Ngrok tunnel
echo whenever Windows starts up.
echo.

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

:: Resolve absolute paths
pushd "%~dp0.."
set "PROJECT_DIR=%CD%"
popd
set "SCRIPT_DIR=%~dp0"
set "RUN_ALL_BAT=%SCRIPT_DIR%run_all.bat"

:: Clean up old separate shortcuts if they exist to prevent race conditions
if exist "%STARTUP_DIR%\CropinServer.lnk" (
    del /f /q "%STARTUP_DIR%\CropinServer.lnk" 2>nul
)
if exist "%STARTUP_DIR%\CropinNgrok.lnk" (
    del /f /q "%STARTUP_DIR%\CropinNgrok.lnk" 2>nul
)

echo [1/3] Creating Windows Startup Shortcut for Unified Launcher (run_all.bat)...
powershell -NoProfile -Command ^
  "$ws = New-Object -COM WScript.Shell;" ^
  "$s = $ws.CreateShortcut('%STARTUP_DIR%\CropinAutomation.lnk');" ^
  "$s.TargetPath = '%RUN_ALL_BAT%';" ^
  "$s.WorkingDirectory = '%PROJECT_DIR%';" ^
  "$s.Description = 'Cropin Automation Server and Ngrok Orchestrator';" ^
  "$s.WindowStyle = 1;" ^
  "$s.Save()"

if %errorlevel% equ 0 (
    echo       [OK] Shortcut created: '%STARTUP_DIR%\CropinAutomation.lnk'
) else (
    echo       [WARNING] Could not create startup shortcut via PowerShell.
)

echo.
echo [2/3] Registering Windows Scheduled Task (Runs on Logon with Highest Privileges)...
schtasks /create /tn "CropinAutomationServer" /tr "\"%RUN_ALL_BAT%\"" /sc onlogon /rl highest /f >nul 2>&1
if %errorlevel% equ 0 (
    echo       [OK] Scheduled Task 'CropinAutomationServer' created successfully.
) else (
    echo       [INFO] Task Scheduler registration skipped (requires Admin). Startup folder shortcut will be used.
)

echo.
echo [3/3] Checking Unattended Auto-Logon...
echo ========================================================
echo  IMPORTANT: Unattended Server Reboots
echo ========================================================
echo  Windows Startup shortcuts and tasks only trigger when a user logs in.
echo  If this computer restarts automatically (e.g., Windows Update)
echo  and remains on the Lock Screen, the server will NOT run
echo  unless Windows Auto-Logon is enabled.
echo.
echo  Would you like to configure Windows Auto-Logon now?
set /p CONFIGURE_AUTOLOGON="  Configure Auto-Logon? (Y/N, default Y): "
if /i "%CONFIGURE_AUTOLOGON%"=="N" goto :FINISH

if exist "%SCRIPT_DIR%configure_windows_autologon.bat" (
    call "%SCRIPT_DIR%configure_windows_autologon.bat"
)

:FINISH
echo.
echo ========================================================
echo  Auto-Start setup completed!
echo  Next time this machine restarts, both Server and Ngrok
echo  will automatically start in sequence.
echo ========================================================
echo.
pause
