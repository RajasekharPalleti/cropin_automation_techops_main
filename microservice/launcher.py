"""
Cropin Automation Launcher Microservice
----------------------------------------
Runs on port 4445 (always-on, lightweight).
Friend's website button calls this to start the main app on port 4444.

Usage:
    python launcher.py
    OR: uvicorn launcher:app --host 0.0.0.0 --port 4445
"""

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LAUNCHER_PORT = int(os.environ.get("LAUNCHER_PORT", 4445))
APP_PORT = int(os.environ.get("APP_PORT", 4444))

# Absolute path to the main app directory.
# The launcher.py lives inside  <app_root>/microservice/launcher.py
# so the app root is one level up.
APP_ROOT = Path(__file__).resolve().parent.parent
APP_MAIN = APP_ROOT / "app" / "main.py"

# How long (seconds) to wait for the app to become reachable after launch
APP_STARTUP_TIMEOUT = 60

_app_process: subprocess.Popen | None = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _port_open(port: int) -> bool:
    """Return True if something is already listening on *port*."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _start_app() -> None:
    """Start the main app as a detached subprocess."""
    global _app_process

    # Already running – nothing to do
    if _port_open(APP_PORT):
        return

    # Kill a stale handle if it exited on its own
    if _app_process is not None and _app_process.poll() is not None:
        _app_process = None

    if _app_process is not None:
        return  # still running (or so we think)

    cmd = [
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", str(APP_PORT),
    ]

    # On Windows avoid a console pop-up window
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    log_path = APP_ROOT / "microservice" / "app_launcher.log"
    log_file = open(log_path, "a")

    _app_process = subprocess.Popen(
        cmd,
        cwd=str(APP_ROOT),
        stdout=log_file,
        stderr=log_file,
        creationflags=creation_flags,
    )


def _stop_app() -> None:
    """Terminate the main app process."""
    global _app_process
    if _app_process is not None:
        _app_process.terminate()
        try:
            _app_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _app_process.kill()
        _app_process = None


async def _wait_for_app(timeout: int = APP_STARTUP_TIMEOUT) -> bool:
    """Poll until the app port is open or *timeout* seconds elapse."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(APP_PORT):
            return True
        await asyncio.sleep(1)
    return False


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Cropin Automation Launcher", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    # Lock this down to your friend's website origin in production,
    # e.g. allow_origins=["http://localhost:3000", "https://myfriend.com"]
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Serve the JS widget so friend's site can <script src="…/widget.js">
_widget_path = Path(__file__).parent / "button_widget.js"
if _widget_path.exists():
    @app.get("/widget.js", include_in_schema=False)
    def serve_widget():
        return FileResponse(str(_widget_path), media_type="application/javascript")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/status")
def status():
    """
    Returns whether the main app is currently running.
    Friend's button polls this to decide its label/colour.
    """
    running = _port_open(APP_PORT)
    return {
        "running": running,
        "app_url": f"http://localhost:{APP_PORT}",
        "app_port": APP_PORT,
    }


@app.post("/api/launch")
async def launch():
    """
    Start the main app (idempotent – safe to call if already running).
    Waits until the app is reachable, then returns its URL.
    """
    if _port_open(APP_PORT):
        return JSONResponse({
            "status": "already_running",
            "app_url": f"http://localhost:{APP_PORT}",
        })

    _start_app()
    ready = await _wait_for_app()

    if not ready:
        return JSONResponse(
            {"status": "error", "message": "App did not start within the timeout."},
            status_code=503,
        )

    return JSONResponse({
        "status": "launched",
        "app_url": f"http://localhost:{APP_PORT}",
    })


@app.post("/api/stop")
def stop():
    """Stop the main app (only if it was started by this launcher)."""
    _stop_app()
    return {"status": "stopped"}


@app.get("/api/health")
def health():
    """Launcher liveness probe."""
    return {"launcher": "ok", "launcher_port": LAUNCHER_PORT}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("launcher:app", host="0.0.0.0", port=LAUNCHER_PORT, reload=False)
