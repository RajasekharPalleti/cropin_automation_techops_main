"""
app/routes.py
-------------
All FastAPI API route handlers for the Cropin Automation TechOps platform.
The router is registered in main.py via app.include_router(router).
"""

import os
import ast
import json
import shutil
import asyncio
import importlib.util

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.core.auth import get_access_token
from app.script_configs import (
    SCRIPT_CONFIGS, DEFAULT_SCRIPT_CONFIG,
    SCRIPTS_DIR, UPLOAD_DIR, OUTPUT_DIR, TEMPLATES_DIR,
)
from app.state import JobStoppedException, manager, backup_manager

router = APIRouter()


# ---------------------------------------------------------------------------
# Background job runner
# ---------------------------------------------------------------------------

async def process_background_script(
    script_path: str,
    script_name: str,
    input_path: str,
    output_path: str,
    output_filename: str,
    config_dict: dict,
    client_id: str,
):
    try:
        # --- Authentication ---
        username = config_dict.get("username")
        password = config_dict.get("password")
        environment = config_dict.get("environment")
        tenant_code = config_dict.get("tenant_code")

        await manager.send_log(f"Authenticating user: {username}...", client_id)

        if username and password and tenant_code:
            try:
                token = get_access_token(tenant_code, username, password, environment)
                if token:
                    config_dict["token"] = token
                    await manager.send_log("Authentication successful.", client_id)
                else:
                    raise Exception("Authentication failed: No token returned.")
            except Exception as auth_err:
                await manager.send_log(f"JOB_FAILED::Authentication failed: {str(auth_err)}", client_id)
                return

        loop = asyncio.get_running_loop()

        # Log callback used by blocking script threads to push messages safely
        def log_callback(message):
            if manager.is_cancelled(client_id):
                print(f"DEBUG: Raising Stop Exception for {client_id}")
                raise JobStoppedException("Job Stopped by User")
            try:
                asyncio.run_coroutine_threadsafe(manager.send_log(message, client_id), loop)
            except Exception as e:
                print(f"Log Error: {e}")

        # --- Load and run the script module dynamically ---
        spec = importlib.util.spec_from_file_location("module.name", script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "run"):
            await manager.send_log(f"Starting execution of {script_name}...", client_id)

            def run_wrapper():
                import inspect
                sig = inspect.signature(module.run)
                if "log_callback" in sig.parameters:
                    module.run(input_path, output_path, config_dict, log_callback=log_callback)
                else:
                    module.run(input_path, output_path, config_dict)

            await asyncio.to_thread(run_wrapper)
            await manager.send_log("Script execution finished.", client_id)

            if os.path.exists(output_path):
                await manager.send_log(f"JOB_COMPLETED::{output_filename}", client_id)

                # Backup output file to Google Drive
                await manager.send_log("Backing up output file to Drive...", client_id)
                backup_manager.upload_file(output_path)

                # Backup input file if it exists
                if input_path and os.path.exists(input_path):
                    await manager.send_log("Backing up input file to Drive...", client_id)
                    backup_manager.upload_file(input_path)

                await manager.send_log("Backup completed.", client_id)
        else:
            await manager.send_log("JOB_FAILED::Script does not have a 'run' function", client_id)

    except JobStoppedException:
        await manager.send_log("JOB_STOPPED::Execution stopped by user.", client_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        await manager.send_log(f"JOB_FAILED::Error: {str(e)}", client_id)
    finally:
        manager.mark_inactive(client_id)


# ---------------------------------------------------------------------------
# SSE / session management endpoints
# ---------------------------------------------------------------------------

@router.get("/api/logs/{client_id}")
async def sse_endpoint(client_id: str, request: Request):
    """Server-Sent Events stream — clients subscribe here to receive live logs."""
    last_event_id = request.headers.get("Last-Event-ID")
    await manager.connect(client_id, last_event_id)
    return StreamingResponse(manager.stream_logs(client_id), media_type="text/event-stream")


@router.get("/api/status/{client_id}")
async def get_task_status(client_id: str):
    """Check whether a script is currently running for a given client."""
    return {"is_running": manager.is_active(client_id)}


@router.post("/api/clear_session/{client_id}")
async def clear_session(client_id: str):
    """Clear log history and mark the client as inactive."""
    manager.clear_logs(client_id)
    manager.mark_inactive(client_id)
    return {"status": "cleared"}


@router.post("/api/stop/{client_id}")
async def stop_execution(client_id: str):
    """Request cancellation of a running script for a given client."""
    if manager.is_active(client_id):
        manager.request_cancel(client_id)
        return {"status": "stopping", "message": "Stop requested. Process will terminate shortly."}
    return {"status": "ignored", "message": "No active process found."}


# ---------------------------------------------------------------------------
# Server control endpoints for Auto-Updater
# ---------------------------------------------------------------------------

@router.get("/api/server/status")
async def get_server_status():
    """Check how many background script jobs are currently running."""
    return {"active_jobs": len(manager.active_tasks)}


@router.post("/api/server/shutdown")
async def shutdown_server():
    """Request the Uvicorn server to shut down via stop_server.bat."""
    import os
    import subprocess
    import threading

    def kill_server():
        print("Shutdown requested via API. Executing stop_server.bat...")
        try:
            bat_path = os.path.abspath(os.path.join("batch_scripts", "stop_server.bat"))
            if os.path.exists(bat_path):
                # We pipe 'echo .' to bypass the 'pause' at the end of the bat file
                subprocess.Popen(f'echo. | "{bat_path}"', shell=True)
            else:
                print(f"{bat_path} not found! Doing hard exit.")
                os._exit(0)
        except Exception as e:
            print(f"Error running batch script: {e}")
            os._exit(0)

    # Run in a background thread so the HTTP response can be sent first
    threading.Timer(2.0, kill_server).start()
    return {"status": "shutting_down", "message": "Server will shut down via stop_server.bat in 2 seconds."}


# ---------------------------------------------------------------------------
# Session recovery
# ---------------------------------------------------------------------------

class RecoveryRequest(BaseModel):
    machine_id: str
    username: str
    tenant_code: str


@router.post("/api/recover_session")
async def recover_session(request: RecoveryRequest):
    """Reconnect a browser tab to an already-running job on the same machine."""
    if not request.machine_id or not request.username or not request.tenant_code:
        return {"found": False}

    target_key = f"{request.tenant_code}:{request.username}:{request.machine_id}"

    for client_id, machine_key in manager.client_machine_map.items():
        if machine_key == target_key and manager.is_active(client_id):
            script_name = manager.client_script_map.get(client_id, "Unknown Script")
            return {"found": True, "client_id": client_id, "script_name": script_name}

    return {"found": False}


# ---------------------------------------------------------------------------
# Script listing and templates
# ---------------------------------------------------------------------------

@router.get("/api/scripts")
async def list_scripts():
    """Return all available scripts with their API config and docstring details."""
    scripts = []
    # Script-specific configs are maintained in app/script_configs.py

    for filename in os.listdir(SCRIPTS_DIR):
        if filename.endswith(".py") and filename != "__init__.py":
            filepath = os.path.join(SCRIPTS_DIR, filename)
            description = "No description available."
            input_description = "Standard Excel Input."

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())
                    docstring = ast.get_docstring(tree)
                    if docstring:
                        parts = docstring.split("Inputs:")
                        description = parts[0].strip()
                        if len(parts) > 1:
                            input_description = parts[1].strip()
            except Exception as e:
                print(f"Error parsing docstring for {filename}: {e}")

            config = SCRIPT_CONFIGS.get(filename, DEFAULT_SCRIPT_CONFIG)
            scripts.append({
                "name": filename,
                "url": config["url"],
                "label": config["label"],
                "url2": config.get("url2"),
                "label2": config.get("label2"),
                "requires_input": config.get("requires_input", True),
                "description": description,
                "input_description": input_description,
                # Dynamic UI Flags
                "show_extended_config": config.get("show_extended_config", False),
                "extended_config_type": config.get("extended_config_type", ""),
                "show_pr_weather": config.get("show_pr_weather", False),
                "show_attribute_config": config.get("show_attribute_config", False),
                "show_address_config": config.get("show_address_config", False),
                "show_area_audit": config.get("show_area_audit", False),
                "show_variety_removal": config.get("show_variety_removal", False),
                "show_ca_close_delete": config.get("show_ca_close_delete", False),
                "show_time_delay": config.get("show_time_delay", True)
            })

    scripts.sort(key=lambda x: x["name"])
    return {"scripts": scripts}


@router.get("/api/template/{script_name}")
async def get_template(script_name: str):
    """Download the Excel input template for a given script."""
    template_filename = script_name.replace(".py", ".xlsx")
    template_path = os.path.join(TEMPLATES_DIR, template_filename)

    if os.path.exists(template_path):
        return FileResponse(
            template_path,
            filename=template_filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    raise HTTPException(
        status_code=404,
        detail=f"Template not found for {script_name}. Please add {template_filename} to sample_templates folder.",
    )


# ---------------------------------------------------------------------------
# File upload / download
# ---------------------------------------------------------------------------

@router.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Accept an input Excel file and save it to the uploads directory."""
    input_filename = f"input_{file.filename}"
    input_path = os.path.join(UPLOAD_DIR, input_filename)
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"filename": file.filename, "server_path": input_filename}


@router.get("/api/download/{filename}")
async def download_result(filename: str):
    """Download a generated output Excel file."""
    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(
            file_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    raise HTTPException(status_code=404, detail="File not found")


# ---------------------------------------------------------------------------
# Backup listing
# ---------------------------------------------------------------------------

@router.get("/api/backups")
async def get_backups(page_size: int = 100, page_token: str = None):
    """List backed-up files from Google Drive."""
    return backup_manager.list_files(page_size=page_size, page_token=page_token)


# ---------------------------------------------------------------------------
# Script execution
# ---------------------------------------------------------------------------

@router.post("/api/execute")
async def execute_script(
    background_tasks: BackgroundTasks,
    script_name: str = Form(...),
    input_filename: str = Form(None),
    config: str = Form(...),
    client_id: str = Form(...),
    machine_id: str = Form(None),
):
    """Validate the request, acquire locks, then queue the script as a background task."""

    # Clear previous logs for this client — new run starts fresh
    manager.clear_logs(client_id)

    # Prevent concurrent execution on the same browser tab
    if manager.is_active(client_id):
        raise HTTPException(status_code=409, detail="A script is already running on this tab.")

    try:
        try:
            config_dict = json.loads(config)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid config JSON")

        # --- Machine-based locking: one script per user per machine ---
        tenant = config_dict.get("tenant_code", "unknown")
        user = config_dict.get("username", "unknown")
        machine_lock_key = None

        if machine_id:
            machine_lock_key = f"{tenant}:{user}:{machine_id}"
            if manager.is_machine_active(machine_lock_key):
                raise HTTPException(
                    status_code=409,
                    detail="MACHINE LOCK: You already have a script running on this computer. "
                           "Please wait for it to finish or use a different computer.",
                )
            manager.mark_active(client_id, machine_lock_key, script_name)
        else:
            manager.mark_active(client_id, None, script_name)

        script_path = os.path.join(SCRIPTS_DIR, script_name)
        if not os.path.exists(script_path):
            manager.mark_inactive(client_id)
            raise HTTPException(status_code=404, detail="Script not found")

        # Derive input/output paths
        input_path = None
        if input_filename:
            base_name = os.path.splitext(input_filename)[0]
            output_filename = f"{base_name}_Output.xlsx"
            input_path = os.path.join(UPLOAD_DIR, f"input_{input_filename}")
            if not os.path.exists(input_path):
                manager.mark_inactive(client_id)
                raise HTTPException(status_code=404, detail="Input file not found")
        else:
            output_filename = f"{script_name.replace('.py', '')}_Output.xlsx"

        output_path = os.path.join(OUTPUT_DIR, output_filename)

        background_tasks.add_task(
            process_background_script,
            script_path,
            script_name,
            input_path,
            output_path,
            output_filename,
            config_dict,
            client_id,
        )

        return {"status": "queued", "message": "Script execution started in background"}

    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": f"Internal Server Error: {str(e)}"})


# ---------------------------------------------------------------------------
# Server Logs Viewer Route
# ---------------------------------------------------------------------------

@router.get("/api/server_logs")
async def get_server_logs(offset_line: int = 0, limit: int = 1000):
    """
    Returns lines from the server.log file, reading from the end backwards.
    - offset_line: How many lines from the end to skip (default 0 = latest logs). 
                   e.g., offset_line=1000 means skip the last 1000 lines and get the block before that.
    - limit: How many lines to return in this batch (default 1000).
    """
    log_path = "server.log"
    if not os.path.exists(log_path):
        return {"logs": ["Log file not found."], "total_lines": 0}

    try:
        lines = []
        # Attempt to load older rotated logs first
        if os.path.exists("server.log.1"):
            with open("server.log.1", "r", encoding="utf-8", errors="replace") as f:
                lines.extend(f.readlines())
                
        # Load the current active logs
        if os.path.exists("server.log"):
            with open("server.log", "r", encoding="utf-8", errors="replace") as f:
                lines.extend(f.readlines())
            
        total_lines = len(lines)
        
        # If the offset pushes us past the start of the file, we return nothing
        if offset_line >= total_lines:
            return {"logs": [], "total_lines": total_lines}
        
        # Start and end indexes for our slice
        end_idx = total_lines - offset_line
        start_idx = max(0, end_idx - limit)
        
        # Slice the list of lines
        chunk = lines[start_idx:end_idx]
        
        return {
            "logs": chunk,
            "total_lines": total_lines,
            "returned_count": len(chunk)
        }
            
    except Exception as e:
        return {"logs": [f"Error reading log file: {str(e)}"], "total_lines": 0}


@router.get("/api/server_logs/stream")
async def stream_server_logs(request: Request):
    """
    SSE endpoint that pushes new lines from server.log to the client as they are written.
    """
    from fastapi.responses import StreamingResponse
    import asyncio
    
    log_path = "server.log"

    async def event_generator():
        # Wait a moment if file doesn't exist yet before crashing
        if not os.path.exists(log_path):
            await asyncio.sleep(1)
            
        if not os.path.exists(log_path):
            yield f"data: Log file not found.\n\n"
            return

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            # Move immediately to the end of the file, we only want *new* logs from here on
            f.seek(0, os.SEEK_END)
            
            while True:
                # If client disconnected, stop generating
                if await request.is_disconnected():
                    break
                    
                line = f.readline()
                if line:
                    # SSE format requires "data: <payload>\n\n"
                    # We send just the raw line and let the frontend format it
                    import json
                    # We wrap the payload in JSON to safely encode newlines and quotes
                    payload = json.dumps({"line": line.rstrip()})
                    yield f"data: {payload}\n\n"
                else:
                    # Wait briefly before trying again
                    await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")



# ---------------------------------------------------------------------------
# Static / root
# ---------------------------------------------------------------------------

@router.get("/")
async def read_root():
    """Serve the main single-page application."""
    return FileResponse("static/index.html")
