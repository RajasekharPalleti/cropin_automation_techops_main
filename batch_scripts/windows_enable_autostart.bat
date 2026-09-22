@echo off
setlocal EnableDelayedExpansion
title Cropin Server - Windows Auto-Start & Auto-Logon Setup

:: 1. Ensure Administrator Privileges (Self-Elevate if double-clicked)
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Elevating to Administrator...
    powershell -NoProfile -Command "Start-Process -FilePath cmd.exe -ArgumentList '/k cd /d \"\"%~dp0\"\" && \"\"%~nx0\"\" \"%USERNAME%\" \"%USERDOMAIN%\"' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
pushd ..
set "PROJECT_DIR=%CD%"
popd
set "SCRIPT_DIR=%~dp0"
set "RUN_ALL_BAT=%SCRIPT_DIR%run_all.bat"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

:: Get logged in user (passed from initial invocation before elevation)
set "TARGET_USER=%USERNAME%"
set "TARGET_DOMAIN=%USERDOMAIN%"
if not "%~1"=="" set "TARGET_USER=%~1"
if not "%~2"=="" set "TARGET_DOMAIN=%~2"

echo ========================================================
echo  Cropin Server - Windows Auto-Start Setup
echo ========================================================
echo  Target User:   %TARGET_USER%
echo  Target PC:     %TARGET_DOMAIN%
echo  Project Root:  %PROJECT_DIR%
echo ========================================================
echo.

:: 2. Clean up legacy separate shortcuts
if exist "%STARTUP_DIR%\CropinServer.lnk" del /f /q "%STARTUP_DIR%\CropinServer.lnk" 2>nul
if exist "%STARTUP_DIR%\CropinNgrok.lnk" del /f /q "%STARTUP_DIR%\CropinNgrok.lnk" 2>nul

:: 3. Create Windows Startup Folder shortcut for run_all.bat
echo [1/3] Creating Windows Startup shortcut...
powershell -NoProfile -Command "$ws = New-Object -COM WScript.Shell; $s = $ws.CreateShortcut('%STARTUP_DIR%\CropinAutomation.lnk'); $s.TargetPath = '%RUN_ALL_BAT%'; $s.WorkingDirectory = '%PROJECT_DIR%'; $s.WindowStyle = 1; $s.Save()"
if %errorlevel% equ 0 (
    echo       [OK] Shortcut created in Startup folder.
) else (
    echo       [WARNING] Could not create shortcut via PowerShell.
)

:: 4. Register Windows Scheduled Task (Runs on Logon with Highest Privileges)
echo.
echo [2/3] Registering Windows Scheduled Task...
schtasks /create /tn "CropinAutomationServer" /tr "\"%RUN_ALL_BAT%\"" /sc onlogon /rl highest /f >nul 2>&1
if %errorlevel% equ 0 (
    echo       [OK] Scheduled Task 'CropinAutomationServer' created successfully.
) else (
    echo       [INFO] Task Scheduler registration skipped.
)

:: 5. Configure Windows Auto-Logon
echo.
echo [3/3] Configuring Windows Auto-Logon...
echo ========================================================
echo  Auto-Logon ensures Windows automatically logs into
echo  '%TARGET_USER%' whenever the computer restarts,
echo  so the server and ngrok start completely unattended.
echo ========================================================
echo.

:: Unlock the passwordless checkbox in netplwiz for Win 10/11
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device" /v DevicePasswordLessBuildVersion /t REG_DWORD /d 0 /f >nul 2>&1

echo Please enter the Windows password for '%TARGET_USER%'.
echo (If you do not wish to set Auto-Logon now, simply press Enter to skip).
echo.
set /p "TARGET_PASS=Enter Windows Password for %TARGET_USER%: "

if not "%TARGET_PASS%"=="" (
    reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /t REG_SZ /d "1" /f >nul
    reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v ForceAutoLogon /t REG_SZ /d "1" /f >nul
    reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultUserName /t REG_SZ /d "%TARGET_USER%" /f >nul
    reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword /t REG_SZ /d "%TARGET_PASS%" /f >nul
    reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultDomainName /t REG_SZ /d "%TARGET_DOMAIN%" /f >nul
    
    echo.
    echo ========================================================
    echo  [SUCCESS] Windows Auto-Logon configured for %TARGET_USER%!
    echo  The computer will now log in automatically on boot.
    echo ========================================================
) else (
    echo.
    echo [INFO] Auto-Logon password skipped.
    echo You can configure it later or use Windows 'netplwiz'.
)

echo.
echo ========================================================
echo  All setup completed!
echo ========================================================
echo.
pause
