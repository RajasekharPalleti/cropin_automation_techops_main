@echo off
setlocal EnableDelayedExpansion
title Cropin Server - Windows Auto-Logon Setup

:: 1. Ensure Administrator Privileges (Self-Elevate with persistent /k window)
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Elevating to Administrator
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/k cd /d """%~dp0.""" && """%~f0""" """%USERNAME%""" """%USERDOMAIN%"""' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

:: Capture target user (passed from non-elevated session or current)
set "TARGET_USER=%USERNAME%"
set "TARGET_DOMAIN=%USERDOMAIN%"
if not "%~1"=="" set "TARGET_USER=%~1"
if not "%~2"=="" set "TARGET_DOMAIN=%~2"

echo ========================================================
echo  Cropin Server - Windows Auto-Logon Setup
echo ========================================================
echo  Target User:   %TARGET_USER%
echo  Target PC:     %TARGET_DOMAIN%
echo ========================================================
echo.

:: Unlock passwordless checkbox in netplwiz for Win 10/11
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device" /v DevicePasswordLessBuildVersion /t REG_DWORD /d 0 /f >nul 2>&1

echo [1] Enter Password to Enable Auto-Logon
echo [2] Open Windows Built-in 'netplwiz' Tool (GUI)
echo [3] Disable Auto-Logon
echo [4] Exit
echo.
set /p "CHOICE=Select an option (1-4, default 1): "
if "%CHOICE%"=="" set CHOICE=1

if "%CHOICE%"=="1" goto :SET_PASSWORD
if "%CHOICE%"=="2" goto :RUN_NETPLWIZ
if "%CHOICE%"=="3" goto :DISABLE_LOGON
if "%CHOICE%"=="4" exit /b
goto :EOF

:SET_PASSWORD
echo.
echo Please enter the Windows password for '%TARGET_USER%':
set /p "TARGET_PASS=Password: "

if "%TARGET_PASS%"=="" (
    echo [ERROR] Password cannot be blank.
    pause
    exit /b 1
)

reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /t REG_SZ /d "1" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v ForceAutoLogon /t REG_SZ /d "1" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultUserName /t REG_SZ /d "%TARGET_USER%" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword /t REG_SZ /d "%TARGET_PASS%" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultDomainName /t REG_SZ /d "%TARGET_DOMAIN%" /f >nul

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo  [SUCCESS] Auto-Logon configured for %TARGET_USER%!
    echo ========================================================
) else (
    echo [ERROR] Failed to update registry keys.
)
echo.
pause
exit /b

:RUN_NETPLWIZ
echo Opening netplwiz
start netplwiz.exe
pause
exit /b

:DISABLE_LOGON
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /t REG_SZ /d "0" /f >nul
reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword /f >nul 2>&1
echo [SUCCESS] Auto-Logon disabled.
pause
exit /b
