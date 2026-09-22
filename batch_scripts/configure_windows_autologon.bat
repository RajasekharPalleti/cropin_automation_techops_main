@echo off
title Windows Auto-Logon Configuration
echo ========================================================
echo  Cropin Server - Windows Auto-Logon Setup
echo ========================================================
echo.
echo This tool configures your Windows server machine to
echo automatically log in when the machine reboots (e.g., after
echo a Windows Update, power outage, or system restart).
echo.
echo Once Auto-Logon is enabled, your user desktop loads
echo automatically on reboot, triggering the Cropin Server
echo and Ngrok to start without requiring anyone to enter a password.
echo ========================================================
echo.

:: Check for Administrative privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Requesting Administrative Privileges...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

:: Unhide the 'Users must enter a username and password' checkbox in netplwiz for Win 10/11
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device" /v DevicePasswordLessBuildVersion /t REG_DWORD /d 0 /f >nul 2>&1

echo [1] Configure Auto-Logon (Enter Username and Password - Secure Masked Input)
echo [2] Open Windows Built-in 'netplwiz' Tool (GUI)
echo [3] Disable Auto-Logon (Revert to standard password prompt)
echo [4] Exit
echo.
set /p CHOICE="Select an option (1-4): "

if "%CHOICE%"=="1" goto :SETUP_REGISTRY
if "%CHOICE%"=="2" goto :OPEN_NETPLWIZ
if "%CHOICE%"=="3" goto :DISABLE_AUTOLOGON
if "%CHOICE%"=="4" exit /b
goto :EOF

:SETUP_REGISTRY
echo.
echo --------------------------------------------------------
echo Enter Login Credentials for Automatic Startup:
echo --------------------------------------------------------
echo Current Windows User: %USERNAME%
echo Current Machine/Domain: %USERDOMAIN%
echo (Note: For Microsoft Accounts e.g. Outlook/Work accounts, enter full email)
echo.

set /p INPUT_USER="Username / Email (Press Enter for '%USERNAME%'): "
if "%INPUT_USER%"=="" set INPUT_USER=%USERNAME%

set /p INPUT_DOMAIN="Domain/Computer Name (Press Enter for '%USERDOMAIN%'): "
if "%INPUT_DOMAIN%"=="" set INPUT_DOMAIN=%USERDOMAIN%

echo.
echo Enter Windows Password for %INPUT_USER%:
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$user = '%INPUT_USER%';" ^
  "$domain = '%INPUT_DOMAIN%';" ^
  "$password = Read-Host -Prompt 'Password (hidden)' -AsSecureString;" ^
  "if ($password.Length -eq 0) { Write-Host '[ERROR] Password cannot be empty!' -ForegroundColor Red; exit 1 };" ^
  "$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($password);" ^
  "$plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR);" ^
  "[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR);" ^
  "$regPath = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon';" ^
  "Set-ItemProperty -Path $regPath -Name 'AutoAdminLogon' -Value '1' -Type String -Force;" ^
  "Set-ItemProperty -Path $regPath -Name 'ForceAutoLogon' -Value '1' -Type String -Force;" ^
  "Set-ItemProperty -Path $regPath -Name 'DefaultUserName' -Value $user -Type String -Force;" ^
  "Set-ItemProperty -Path $regPath -Name 'DefaultPassword' -Value $plainPassword -Type String -Force;" ^
  "Set-ItemProperty -Path $regPath -Name 'DefaultDomainName' -Value $domain -Type String -Force;" ^
  "Write-Host '[SUCCESS] AutoLogon registry keys updated securely!' -ForegroundColor Green;"

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo  SUCCESS! Windows Auto-Logon configured for %INPUT_USER%.
    echo  The computer will now log in automatically on boot!
    echo ========================================================
) else (
    echo.
    echo [ERROR] Configuration cancelled or failed.
)
echo.
pause
exit /b

:OPEN_NETPLWIZ
echo.
echo Opening Windows User Accounts (netplwiz)...
echo (The passwordless checkbox has been unlocked for Windows 10/11)
echo.
echo Instructions:
echo  1. Select your username from the list.
echo  2. UNCHECK "Users must enter a user name and password to use this computer".
echo  3. Click "Apply".
echo  4. Enter your password when prompted and click OK.
echo.
start netplwiz.exe
pause
exit /b

:DISABLE_AUTOLOGON
echo.
echo Disabling Auto-Logon...
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /t REG_SZ /d "0" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v ForceAutoLogon /t REG_SZ /d "0" /f >nul
reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword /f >nul 2>&1
echo Auto-Logon has been disabled. Windows will require a password on boot.
pause
exit /b
