:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
echo "Starting Cropin Automation Server..."
echo "Open http://localhost:4444 or http://<your-ip>:4444 in your browser."
cd "$(dirname "$0")/.."
python3 -m app.main
read -p "Press any key to close..."
exit 0

:WINDOWS
echo Starting Cropin Automation Server...
echo Open http://localhost:4444 or http://<your-ip>:4444 in your browser.
pushd %~dp0\..\
python -m app.main
popd
pause
