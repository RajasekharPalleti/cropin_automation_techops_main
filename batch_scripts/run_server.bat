:<<"::WINDOWS_ONLY"
@echo off
goto :WINDOWS
::WINDOWS_ONLY

# Mac/Linux script
echo "Starting Cropin Automation Server..."
echo "Open http://localhost:4444 or http://<your-ip>:4444 in your browser."
cd "$(dirname "$0")/.."

echo "Activating virtual environment..."
if [ ! -d ".venv" ]; then
    echo "Creating new virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "Installing/Updating requirements..."
pip3 install -r requirements.txt
python3 -m app.main
read -p "Press any key to close..."
exit 0

:WINDOWS
echo Starting Cropin Automation Server...
echo Open http://localhost:4444 or http://<your-ip>:4444 in your browser.
pushd %~dp0\..\
echo Installing/Updating requirements...
pip install -r requirements.txt
python -m app.main
popd
pause
