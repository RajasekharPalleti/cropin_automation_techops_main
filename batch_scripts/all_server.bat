:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux: run run_all.bat
DIR="$(dirname "$0")"
exec bash "$DIR/run_all.bat" "$@"

:WINDOWS
@echo off
call "%~dp0run_all.bat" %*
exit /b %ERRORLEVEL%
