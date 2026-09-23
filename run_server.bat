:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux execution
DIR="$(dirname "$0")"
exec bash "$DIR/batch_scripts/run_server.bat" "$@"

:WINDOWS
@echo off
call "%~dp0batch_scripts\run_server.bat" %*
exit /b %ERRORLEVEL%
