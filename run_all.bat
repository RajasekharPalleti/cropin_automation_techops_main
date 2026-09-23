:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux execution
DIR="$(dirname "$0")"
exec bash "$DIR/batch_scripts/run_all.bat" "$@"

:WINDOWS
@echo off
call "%~dp0batch_scripts\run_all.bat" %*
exit /b %ERRORLEVEL%
