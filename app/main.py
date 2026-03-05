"""
app/main.py
-----------
Application entry point.

Responsibilities (ONLY):
  - Auto-install missing dependencies from requirements.txt
  - Define the FastAPI lifespan (startup cleanup + periodic backup task)
  - Create the FastAPI app with CORS middleware and static file mount
  - Register the API router from app.routes

All API route handlers live in  → app/routes.py
Shared state (ConnectionManager) lives in → app/state.py
Script API configs / path constants live in → app/script_configs.py
"""

import sys
import subprocess
import importlib.util
import importlib.metadata
import os
import re
import logging
import logging.handlers
import datetime

# ---------------------------------------------------------------------------
# Setup Logger to write everything to server.log and console
# ---------------------------------------------------------------------------

class LoggerWriter:
    def __init__(self, logger, level, original_stream=None):
        self.logger = logger
        self.level = level
        self._original = original_stream
        self._buffer = ""

    def write(self, message):
        self._buffer += message
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line_str = line.rstrip()
            if line_str != "":
                # Prevent infinite recursion if the internal logger fails and writes to stderr
                if '--- Logging error ---' in line_str or 'RecursionError' in line_str:
                    sys.__stderr__.write(line_str + '\n')
                    continue
                self.logger.log(self.level, line_str)

    def flush(self):
        if self._buffer.rstrip() != "":
            self.logger.log(self.level, self._buffer.rstrip())
            self._buffer = ""
        if self._original:
            self._original.flush()
            
    def isatty(self):
        return False
        
    def __getattr__(self, name):
        if self._original:
            return getattr(self._original, name)
        raise AttributeError(f"'LoggerWriter' object has no attribute '{name}'")

# Ensure basic configuration sends all Python root logs to server.log
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s', # Keep it simple so it matches what user sees in terminal
    handlers=[
        logging.handlers.RotatingFileHandler(
            "server.log", maxBytes=15 * 1024 * 1024, backupCount=1, encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout)
    ]
)

# Redirect standard prints and errors to the logger
sys.stdout = LoggerWriter(logging.getLogger(), logging.INFO, sys.stdout)
sys.stderr = LoggerWriter(logging.getLogger(), logging.ERROR, sys.stderr)


# ---------------------------------------------------------------------------
# Dependency bootstrap — runs before any third-party imports
# ---------------------------------------------------------------------------

def _ensure_dependencies():
    requirements_path = "requirements.txt"
    if not os.path.exists(requirements_path):
        print("Warning: requirements.txt not found. Skipping auto-installation.")
        return

    missing = False
    try:
        with open(requirements_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Parse package name (handles version specifiers like ==, >=, etc.)
                package_name = re.split(r"[=<>~]", line)[0].strip()
                if not package_name:
                    continue

                try:
                    importlib.metadata.distribution(package_name)
                except importlib.metadata.PackageNotFoundError:
                    try:
                        importlib.metadata.distribution(package_name.replace("_", "-"))
                    except importlib.metadata.PackageNotFoundError:
                        try:
                            importlib.metadata.distribution(package_name.replace("-", "_"))
                        except importlib.metadata.PackageNotFoundError:
                            print(f"Missing dependency: {package_name}")
                            missing = True
                            break

    except Exception as e:
        print(f"Error checking dependencies: {e}")

    if missing:
        print("Missing dependencies detected from requirements.txt. Installing...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_path])
            print("Dependencies installed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error installing dependencies: {e}")


_ensure_dependencies()


# ---------------------------------------------------------------------------
# Third-party imports (safe after dependency check)
# ---------------------------------------------------------------------------

import asyncio
import shutil

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.script_configs import (
    UPLOAD_DIR, OUTPUT_DIR,
    CLEANUP_RETENTION_DAYS, CLEANUP_INTERVAL_SECONDS,
    SERVER_HOST, SERVER_PORT,
)
from app.state import manager, backup_manager
from app.routes import router


# ---------------------------------------------------------------------------
# Periodic backup cleanup task (runs once per day in the background)
# ---------------------------------------------------------------------------

async def periodic_cleanup_task():
    while True:
        try:
            print("Executing Scheduled Backup Cleanup (Retention Policy: 3 Months)...")
            # Run in thread because backup_manager may make blocking API calls
            await asyncio.to_thread(backup_manager.cleanup_old_files, days=CLEANUP_RETENTION_DAYS)
        except Exception as e:
            print(f"Scheduled Cleanup Failed: {e}")

        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Lifespan: startup cleanup + background tasks
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Clean up any leftover files from the previous session
    print("Execute Clean up temporary directories...")
    for d in [UPLOAD_DIR, OUTPUT_DIR]:
        if os.path.exists(d):
            for filename in os.listdir(d):
                file_path = os.path.join(d, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"Failed to delete {file_path}. Reason: {e}")

    asyncio.create_task(periodic_cleanup_task())
    yield


# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static assets
app.mount("/static", StaticFiles(directory="static"), name="static")

# Register all API routes
app.include_router(router)


# ---------------------------------------------------------------------------
# Dev server entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
