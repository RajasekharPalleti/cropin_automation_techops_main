@echo off
title Windows Auto-Logon Configuration
echo ========================================================
echo  Cropin Server - Windows Auto-Logon Setup
echo ========================================================
echo.

:: Capture the logged-in username before potential UAC elevation
set "TARGET_USER=%USERNAME%"
set "TARGET_DOMAIN=%USERDOMAIN%"
if not "%~1"=="" set "TARGET_USER=%~1"
if not "%~2"=="" set "TARGET_DOMAIN=%~2"

:: Check for Administrative privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Requesting Administrator Privileges to configure Auto-Logon...
    powershell -Command "Start-Process cmd -ArgumentList '/k \"\"%~f0\"\" \"%TARGET_USER%\" \"%TARGET_DOMAIN%\"' -Verb RunAs"
    exit /b
)

:: Unhide the 'Users must enter a username and password' checkbox in netplwiz for Win 10/11
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device" /v DevicePasswordLessBuildVersion /t REG_DWORD /d 0 /f >nul 2>&1

echo Target Windows User:   %TARGET_USER%
echo Target Domain/PC:      %TARGET_DOMAIN%
echo.
echo Please enter the Windows password for %TARGET_USER% to enable
echo unattended auto-login after system restarts.
echo.

set /p "TARGET_PASS=Enter Windows Password for %TARGET_USER%: "

if "%TARGET_PASS%"=="" (
    echo.
    echo [ERROR] Password cannot be empty!
    echo If your account has NO password, Windows does not require AutoLogon.
    echo.
    echo Opening Windows Netplwiz GUI instead...
    start netplwiz.exe
    pause
    exit /b 1
)

echo.
echo Saving Auto-Logon credentials into Windows registry...

reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /t REG_SZ /d "1" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v ForceAutoLogon /t REG_SZ /d "1" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultUserName /t REG_SZ /d "%TARGET_USER%" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword /t REG_SZ /d "%TARGET_PASS%" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultDomainName /t REG_SZ /d "%TARGET_DOMAIN%" /f >nul

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo  [SUCCESS] Auto-Logon successfully enabled for: %TARGET_USER%
    echo  Whenever this machine reboots, Windows will automatically
    echo  log in and start the Cropin Automation Server + Ngrok!
    echo ========================================================
) else (
    echo.
    echo [ERROR] Could not update registry. Make sure you ran as Administrator.
    echo Launching Windows netplwiz tool as fallback...
    start netplwiz.exe
)

echo.
pause
exit /b
