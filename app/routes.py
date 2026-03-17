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
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile, Body
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

            # 1. Backup input file first (source of truth)
            if input_path and os.path.exists(input_path):
                await manager.send_log("Backing up input file to Drive...", client_id)
                backup_manager.upload_file(input_path)

            # 2. Backup output file
            if os.path.exists(output_path):
                await manager.send_log(f"JOB_COMPLETED::{output_filename}", client_id)
                await manager.send_log("Backing up output file to Drive...", client_id)
                backup_manager.upload_file(output_path)

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
    return StreamingResponse(
        manager.stream_logs(client_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/api/status/{client_id}")
async def get_task_status(client_id: str):
    """Check whether a script is currently running for a given client."""
    is_active = manager.is_active(client_id)
    is_stopping = manager.is_cancelled(client_id)
    
    # Return running if it's active (even if stopping)
    return {
        "is_running": is_active,
        "is_stopping": is_stopping
    }


@router.post("/api/clear_session/{client_id}")
async def clear_session(client_id: str):
    """Clear log history and mark the client as inactive."""
    manager.clear_logs(client_id)
    manager.mark_inactive(client_id)
    return {"status": "cleared"}


@router.post("/api/stop/{client_id}")
async def stop_execution(client_id: str, admin: bool = False):
    """Request cancellation of a running script for a given client, or a Scheduled background job."""
    if client_id.startswith("Scheduled_"):
        real_id = client_id.replace("Scheduled_", "")
        from app.scheduler import load_jobs, save_jobs
        jobs = load_jobs()
        # Find the job that starts with this truncated ID (since we passed job_id[:8] to the frontend)
        target_job_key = next((k for k in jobs.keys() if k.startswith(real_id)), None)
        
        if target_job_key and jobs[target_job_key]["status"] == "running":
            jobs[target_job_key]["status"] = "cancelled"
            jobs[target_job_key]["error"] = "Cancelled forcefully by admin via Background Process UI."
            jobs[target_job_key]["completed_at"] = datetime.now().isoformat()
            save_jobs(jobs)
            
            # Fire the global cancellation flag so the running background script halts immediately
            if manager.is_active(target_job_key):
                manager.request_cancel(target_job_key)
                if admin:
                    await manager.send_log("JOB_STOPPED::Closed forcefully by admin.", target_job_key)
            
            return {"status": "stopping", "message": "Scheduled Job marked as cancelled."}
            
        return {"status": "ignored", "message": "Scheduled Job not running or not found."}

    # Standard Interactive Job Cancellation
    if manager.is_active(client_id):
        manager.request_cancel(client_id)
        if admin:
            await manager.send_log("JOB_STOPPED::Closed forcefully by admin.", client_id)
        return {"status": "stopping", "message": "Stop requested. Process will terminate shortly."}
        
    return {"status": "ignored", "message": "No active process found."}


# ---------------------------------------------------------------------------
# Server control endpoints for Auto-Updater
# ---------------------------------------------------------------------------

@router.get("/api/server/status")
async def get_server_status():
    """Check how many background script jobs are currently running."""
    active_count = len(manager.active_tasks)
    
    # Add scheduled background jobs to the count
    from app.scheduler import load_jobs
    jobs = load_jobs()
    active_count += sum(1 for job in jobs.values() if job.get("status") == "running")
        
    return {"active_jobs": active_count}


@router.get("/api/server/active_jobs")
async def get_active_jobs():
    """Get details of all currently running background script jobs (SSE and Scheduled)."""
    jobs = []
    active_now = list(manager.active_tasks)
    
    # 1. Append active interactive jobs
    for client_id in active_now:
        # DO NOT filter here — we want the UI to show "Stopping..." until it's gone
        is_stopping = manager.is_cancelled(client_id)
            
        script_name = manager.client_script_map.get(client_id, "Unknown Script")
        machine_key = manager.client_machine_map.get(client_id, "Unknown Machine")
        
        parts = machine_key.split(':') if ':' in machine_key else ["unknown", "unknown", machine_key]
        tenant = parts[0]
        user = parts[1]
        machine_id = parts[2]
        
        jobs.append({
            "client_id": client_id,
            "script_name": script_name,
            "tenant": tenant,
            "user": user,
            "machine_id": machine_id,
            "type": "Interactive",
            "is_stopping": is_stopping
        })
        
    # 2. Append running scheduled jobs
    from app.scheduler import load_jobs
    scheduled_jobs = load_jobs()
    for job_id, job in scheduled_jobs.items():
        if job.get("status") == "running":
            is_stopping = manager.is_cancelled(job_id)
            cfg = job.get("config", {})
            jobs.append({
                "client_id": f"Scheduled_{job_id[:8]}",
                "script_name": job.get("script_name", "Unknown Scheduled Script"),
                "tenant": cfg.get("tenant_code", "unknown"),
                "user": cfg.get("username", "unknown"),
                "machine_id": "Server Background",
                "type": "Scheduled",
                "is_stopping": is_stopping
            })
        
    return {"jobs": jobs}


@router.post("/api/server/stop_all")
async def stop_all_jobs():
    """Request cancellation of all running scripts (Interactive and Scheduled) and notify clients."""
    stopped_count = 0
    active_clients = list(manager.active_tasks)

    # 1. Stop all active background processes (Interactive & Scheduled) tracked by the SSE Manager
    for client_id in active_clients:
        if not manager.is_cancelled(client_id):
            manager.request_cancel(client_id)
            await manager.send_log("JOB_STOPPED::Closed forcefully by admin.", client_id)
            stopped_count += 1
            
    # 2. Specifically update the persistent state of Scheduled Jobs in the JSON ledger
    from app.scheduler import load_jobs, save_jobs
    jobs = load_jobs()
    jobs_modified = False
    
    for job_id, job_data in jobs.items():
        if job_data.get("status") == "running":
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = "Cancelled forcefully by admin via 'Stop All Processes'."
            manager.request_cancel(job_id) # Ensure they disappear from list too
            jobs_modified = True
            stopped_count += 1
            
    if jobs_modified:
        save_jobs(jobs)

    return {
        "status": "success",
        "message": f"Stop requested for {stopped_count} active process(es).",
        "stopped_count": stopped_count
    }


@router.post("/api/server/shutdown")
async def shutdown_server():
    """Request the Uvicorn server to shut down via stop_server.bat."""
    import os
    import subprocess
    import threading

    def kill_server():
        print("Shutdown requested via API. Executing stop_server.bat... wait for 10 mins to deployment and refresh the browser for new changes")
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
                "base_api_url": config.get("base_api_url"),
                "label": config["label"],
                "second_base_api_url": config.get("second_base_api_url"),
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
                "show_google_api_config": config.get("show_google_api_config", False),
                "show_threading": config.get("show_threading", False),
                "show_coordinate_order": config.get("show_coordinate_order", False),
                "show_batch_config": config.get("show_batch_config", False),
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


@router.delete("/api/backups")
async def delete_all_backups():
    """Delete all files in the backup folder."""
    count = backup_manager.delete_all_files()
    return {"status": "success", "deleted_count": count}


@router.delete("/api/backups/{file_id}")
async def delete_single_backup(file_id: str):
    """Delete a specific file from the backup folder."""
    success = backup_manager.delete_file(file_id)
    if success:
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Failed to delete file from Google Drive")


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
# Scheduled Script Execution
# ---------------------------------------------------------------------------

@router.post("/api/schedule")
async def schedule_script(
    script_name: str = Form(...),
    input_filename: str = Form(None),
    config: str = Form(...),
    run_time: str = Form(...)  # Expected ISO format YYYY-MM-DDTHH:MM
):
    """Save the script details and permanently archive the input file for a scheduled run."""
    import uuid
    
    try:
        try:
            config_dict = json.loads(config)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid config JSON")

        script_path = os.path.join(SCRIPTS_DIR, script_name)
        if not os.path.exists(script_path):
            raise HTTPException(status_code=404, detail="Script not found")

        # Move uploaded file to permanent scheduling folder
        permanent_input_path = None
        if input_filename:
            temp_input_path = os.path.join(UPLOAD_DIR, f"input_{input_filename}")
            if not os.path.exists(temp_input_path):
                raise HTTPException(status_code=404, detail="Input file not found")
                
            # Move to scheduled_uploads so lifespan cleanup doesn't delete it
            os.makedirs("scheduled_uploads", exist_ok=True)
            permanent_input_path = os.path.join("scheduled_uploads", f"scheduled_{uuid.uuid4().hex[:8]}_{input_filename}")
            shutil.copy2(temp_input_path, permanent_input_path)

        # Build job structure
        job_id = str(uuid.uuid4())
        job_data = {
            "job_id": job_id,
            "script_name": script_name,
            "run_time": run_time,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "config": config_dict,
            "input_file": permanent_input_path
        }

        # Save to JSON
        from app.scheduler import load_jobs, save_jobs
        jobs = load_jobs()
        jobs[job_id] = job_data
        save_jobs(jobs)

        return {"status": "scheduled", "message": f"Script scheduled for {run_time}", "job_id": job_id}

    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": f"Internal Server Error: {str(e)}"})

@router.get("/api/scheduled_jobs")
async def get_scheduled_jobs():
    """Return all scheduled and running jobs."""
    from app.scheduler import load_jobs
    jobs = load_jobs()
    pending = [dict(data, job_id=jid) for jid, data in jobs.items() if data["status"] == "pending"]
    running = [dict(data, job_id=jid) for jid, data in jobs.items() if data["status"] == "running"]
    history = [dict(data, job_id=jid) for jid, data in jobs.items() if data["status"] in ["completed", "failed", "cancelled"]]
    
    # Sort history by completed_at desc
    history.sort(key=lambda x: x.get("completed_at", ""), reverse=True)

    return {"jobs": pending + running + history, "pending": pending, "running": running, "history": history}

@router.delete("/api/scheduled_jobs/{job_id}")
async def delete_scheduled_job(job_id: str):
    from app.scheduler import load_jobs, save_jobs
    jobs = load_jobs()
    if job_id in jobs:
        # Check if file needs cleanup
        input_path = jobs[job_id].get("input_file")
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except:
                pass
        del jobs[job_id]
        save_jobs(jobs)
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Job not found")

@router.patch("/api/scheduled_jobs/{job_id}")
async def update_scheduled_job(job_id: str, run_time: str = Body(..., embed=True)):
    from app.scheduler import load_jobs, save_jobs
    jobs = load_jobs()
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if jobs[job_id]["status"] != "pending":
        raise HTTPException(status_code=400, detail="Only pending jobs can be rescheduled")
        
    jobs[job_id]["run_time"] = run_time
    save_jobs(jobs)
    return {"status": "updated", "message": f"Job rescheduled to {run_time}"}

@router.post("/api/scheduled_jobs/{job_id}/run_now")
async def run_scheduled_job_now(job_id: str):
    """Moves a scheduled job to running state manually."""
    from app.scheduler import load_jobs, process_scheduled_script
    import asyncio
    
    jobs = load_jobs()
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job_data = jobs[job_id]
    if job_data["status"] == "running":
        raise HTTPException(status_code=400, detail="Job is already running")
        
    # Fire and forget directly
    asyncio.create_task(process_scheduled_script(job_id, job_data))
    return {"status": "started", "message": "Manual run triggered"}


# ---------------------------------------------------------------------------
# Server Logs Viewer Route
# ---------------------------------------------------------------------------

@router.get("/api/server_logs")
async def get_server_logs(offset_line: int = 0, limit: int = 2000):
    """
    Returns a paginated slice of log lines from the combined server.log.1 + server.log files.
    Lines are ordered chronologically (oldest first). Pagination works from the END backwards:
      - offset_line=0          → last `limit` lines (newest)
      - offset_line=2000       → lines before the last 2000
    Returns: { logs, total_lines, returned_count, has_more }
    """
    def count_lines(path):
        """Fast line count without loading entire file into memory."""
        count = 0
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for _ in fh:
                count += 1
        return count

    def read_lines_range(path, start, end):
        """Read only lines[start:end] from a file without loading everything."""
        result = []
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= end:
                    break
                if i >= start:
                    result.append(line)
        return result

    try:
        # Build a manifest of (path, line_count) for the files we have, oldest first
        sources = []
        for path in ("server.log.1", "server.log"):
            if os.path.exists(path):
                sources.append((path, count_lines(path)))

        total_lines = sum(c for _, c in sources)

        if total_lines == 0:
            return {"logs": [], "total_lines": 0, "returned_count": 0, "has_more": False}

        if offset_line >= total_lines:
            return {"logs": [], "total_lines": total_lines, "returned_count": 0, "has_more": False}

        # Global start/end index within the combined virtual file
        end_idx   = total_lines - offset_line
        start_idx = max(0, end_idx - limit)

        # Now extract only the needed lines by walking sources
        result = []
        cursor = 0  # absolute line number at start of current source
        for (path, line_count) in sources:
            src_start = cursor
            src_end   = cursor + line_count

            # Overlap between [start_idx, end_idx) and this source [src_start, src_end)
            local_start = max(0, start_idx - src_start)
            local_end   = min(line_count, end_idx - src_start)

            if local_start < local_end:
                result.extend(read_lines_range(path, local_start, local_end))

            cursor = src_end
            if cursor >= end_idx:
                break

        return {
            "logs": result,
            "total_lines": total_lines,
            "returned_count": len(result),
            "has_more": start_idx > 0,
        }

    except Exception as e:
        return {"logs": [f"Error reading log file: {str(e)}"], "total_lines": 0, "returned_count": 0, "has_more": False}



@router.get("/api/server_logs/search")
async def search_server_logs(q: str = "", offset: int = 0, limit: int = 2000):
    """
    Full-file search across server.log.1 + server.log (not just the in-memory cache).
    - q:      search term (case-insensitive)
    - offset: how many matching lines to skip (for pagination)
    - limit:  max matching lines to return (default 1000)
    Returns: { results, total_matched, has_more, next_offset }
    """
    if not q.strip():
        return {"results": [], "total_matched": 0, "has_more": False, "next_offset": 0}

    term = q.strip().lower()
    matched = []
    skipped = 0
    total_matched = 0

    for path in ("server.log.1", "server.log"):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if term in line.lower():
                        total_matched += 1
                        if skipped < offset:
                            skipped += 1
                            continue
                        if len(matched) < limit:
                            matched.append(line.rstrip())
        except Exception:
            continue

    has_more = (offset + len(matched)) < total_matched

    return {
        "results":       matched,
        "total_matched": total_matched,
        "has_more":      has_more,
        "next_offset":   offset + len(matched),
    }


@router.get("/api/server_logs/stream")
async def stream_server_logs(request: Request):
    """
    SSE endpoint that pushes new lines from server.log to the client as they are written.
    Handles log rotation: when server.log is rotated (renamed to server.log.1 and a new
    server.log is created), the stream detects the size shrinkage and reopens the file.
    """
    from fastapi.responses import StreamingResponse
    import asyncio
    import json

    log_path = "server.log"

    async def event_generator():
        # Wait if file doesn't exist yet
        if not os.path.exists(log_path):
            await asyncio.sleep(1)

        if not os.path.exists(log_path):
            yield f"data: {json.dumps({'line': '[Stream] Log file not found.'})}\n\n"
            return

        f = open(log_path, "r", encoding="utf-8", errors="replace")
        # Seek to end — we only want *new* lines from this point on
        f.seek(0, os.SEEK_END)
        current_pos = f.tell()

        try:
            while True:
                # Disconnect check
                if await request.is_disconnected():
                    break

                # --- Rotation detection ---
                # If the file has shrunk below our position, it was rotated.
                try:
                    file_size = os.path.getsize(log_path)
                except OSError:
                    file_size = 0

                if file_size < current_pos:
                    # Log was rotated — reopen and tail from the beginning of new file
                    f.close()
                    await asyncio.sleep(0.5)  # brief wait for new file to be created
                    f = open(log_path, "r", encoding="utf-8", errors="replace")
                    f.seek(0, os.SEEK_END)
                    current_pos = f.tell()
                    # Notify the browser that a rotation happened
                    yield f"data: {json.dumps({'line': '[Log rotated — continuing with new server.log]'})}\n\n"
                    continue

                line = f.readline()
                if line:
                    current_pos = f.tell()
                    payload = json.dumps({"line": line.rstrip()})
                    yield f"data: {payload}\n\n"
                else:
                    await asyncio.sleep(0.5)
        finally:
            f.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )



# ---------------------------------------------------------------------------
# Static / root
# ---------------------------------------------------------------------------

@router.get("/")
async def read_root():
    """Serve the main single-page application."""
    return FileResponse("static/index.html")
