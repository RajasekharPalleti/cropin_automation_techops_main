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
import requests as ext_requests
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
    input_path: str | None,
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
        if spec is None or spec.loader is None:
            raise Exception(f"Could not load script specification or loader for: {script_path}")
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
async def sse_endpoint(client_id: str, request: Request, last_event_id: str = None):
    """Server-Sent Events stream — clients subscribe here to receive live logs."""
    # Accept Last-Event-ID via header (native SSE standard) OR query param
    # (Render's reverse proxy strips custom headers, so query param is the fallback)
    last_event_id = last_event_id or request.headers.get("Last-Event-ID")
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
    
    async def force_detach_later(job_id: str, delay: int = 5):
        await asyncio.sleep(delay)
        if manager.is_cancelled(job_id) and manager.is_active(job_id):
            print(f"DEBUG: Job {job_id} did not stop gracefully in {delay}s. Forcing detach.")
            manager.detach_job(job_id)

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
                # Give it 5 seconds to gracefully stop before forcefully removing it from active state
                asyncio.create_task(force_detach_later(target_job_key, 5))
            
            return {"status": "stopping", "message": "Scheduled Job marked as cancelled and will detach shortly."}
            
        return {"status": "ignored", "message": "Scheduled Job not running or not found."}

    # Standard Interactive Job Cancellation
    if manager.is_active(client_id):
        manager.request_cancel(client_id)
        if admin:
            await manager.send_log("JOB_STOPPED::Closed forcefully by admin.", client_id)
        
        # Give it 5 seconds to naturally raise JobStoppedException and clean up
        asyncio.create_task(force_detach_later(client_id, 5))
        return {"status": "stopping", "message": "Stop requested. Process will detach shortly if unresponsive."}
        
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
                "is_stopping": is_stopping,
                "started_at": job.get("started_at")
            })
        
    return {"jobs": jobs}


@router.post("/api/server/stop_all")
async def stop_all_jobs():
    """Request cancellation of all running scripts (Interactive and Scheduled) and notify clients."""
    stopped_count = 0
    active_clients = list(manager.active_tasks)
    
    async def force_detach_later(job_ids: list, delay: int = 5):
        await asyncio.sleep(delay)
        for job_id in job_ids:
            if manager.is_cancelled(job_id) and manager.is_active(job_id):
                print(f"DEBUG: Job {job_id} did not stop gracefully in global stop_all. Forcing detach.")
                manager.detach_job(job_id)
                
    jobs_to_track = []

    # 1. Stop all active background processes (Interactive & Scheduled) tracked by the SSE Manager
    for client_id in active_clients:
        manager.request_cancel(client_id)
        await manager.send_log("JOB_STOPPED::Closed forcefully by admin.", client_id)
        jobs_to_track.append(client_id)
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
            if job_id not in jobs_to_track:
                jobs_to_track.append(job_id)
            jobs_modified = True
            if job_id not in active_clients:
                stopped_count += 1
            
    if jobs_modified:
        save_jobs(jobs)
        
    if jobs_to_track:
        asyncio.create_task(force_detach_later(jobs_to_track, 5))

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
            bat_path = os.path.abspath("stop_server.bat")
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

@router.post("/api/server/force_restart")
async def force_restart_server():
    """Trigger a standalone force_restart.py logic (stop server/ngrok, then start new instance)."""
    import os
    import subprocess
    import sys

    try:
        # Use Popen to launch it independently
        # We use sys.executable to ensure we use the same python interpreter/venv
        is_windows = os.name == 'nt'
        if is_windows:
            # 0x00000010 is subprocess.CREATE_NEW_CONSOLE on Windows
            subprocess.Popen(
                [sys.executable, "force_restart.py"],
                shell=False,
                creationflags=0x00000010
            )
        else:
            subprocess.Popen(
                [sys.executable, "force_restart.py"],
                shell=False,
                start_new_session=True
            )
        return {"status": "success", "message": "Force restart sequence initiated. Server will reboot in ~10 seconds."}
    except Exception as e:
        print(f"Error triggering force_restart.py: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger restart: {str(e)}")


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
                "unlimited_batch_size": config.get("unlimited_batch_size", False),
                "show_time_delay": config.get("show_time_delay", True),
                "show_valid_types": config.get("show_valid_types", False),
                "hide_auth": config.get("hide_auth", False),
                "hide_template": config.get("hide_template", False)
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
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
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
async def get_backups(page_size: int = 100, page_token: str | None = None):
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
    run_time: str = Form(...),          # Expected ISO format YYYY-MM-DDTHH:MM
    recurrence: str = Form("none"),     # none / daily / weekly
    max_retries: int = Form(1),         # 0 = no retry, 1+ = retry N times
):
    """Save the script details and permanently archive the input file for a scheduled run."""
    import uuid
    
    # Validate run_time is in the future
    try:
        requested_time = datetime.fromisoformat(run_time)
        if requested_time < datetime.now():
            raise HTTPException(status_code=400, detail="Scheduled time must be in the future.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Expected ISO format.")
    
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
            "input_file": permanent_input_path,
            "recurrence": recurrence,
            "max_retries": max_retries,
            "retry_count": 0,
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
    history = [dict(data, job_id=jid) for jid, data in jobs.items() if data["status"] in ["completed", "failed", "cancelled", "missed"]]
    
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
# Weekly Report standalone endpoint
# ---------------------------------------------------------------------------


@router.get("/api/weekly-report/config")
async def get_weekly_report_config():
    config_path = os.path.join("json_config", "weekly_report_config.json")
    example_path = os.path.join("json_config", "weekly_report_config.json.example")
    
    path_to_read = config_path if os.path.exists(config_path) else example_path
    if not os.path.exists(path_to_read):
        return {"error": "No configuration file found."}
        
    try:
        with open(path_to_read, "r") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}

@router.post("/api/weekly-report/config")
async def save_weekly_report_config(request: Request):
    try:
        data = await request.json()
        config_path = os.path.join("json_config", "weekly_report_config.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

@router.post("/api/weekly-report/run")

async def run_weekly_report(action: str = "send"):
    import queue
    import threading
    import importlib.util
    
    q = queue.Queue()
    
    def run_script():
        try:
            script_path = os.path.join("app", "standalone", "Weekly_Report.py")
            if not os.path.exists(script_path):
                q.put("ERROR: Weekly_Report.py not found in app/standalone/\n")
                q.put("DONE")
                return

            spec = importlib.util.spec_from_file_location("weekly_report", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            def log_callback(msg):
                q.put(msg + "\n")
            
            output_path = os.path.join(OUTPUT_DIR, "Weekly_Report_Output.xlsx")
            module.run(None, output_path, {}, log_callback=log_callback, action=action)
            
            # Backup the generated report
            if os.path.exists(output_path):
                from app.state import backup_manager
                q.put("Backing up output to Google Drive...\n")
                backup_manager.upload_file(output_path)
                
            q.put("DONE")
        except Exception as e:
            import traceback
            traceback.print_exc()
            q.put(f"ERROR: {str(e)}\n")
            q.put("DONE")

    threading.Thread(target=run_script, daemon=True).start()

    async def log_generator():
        while True:
            line = await asyncio.to_thread(q.get)
            if line == "DONE":
                break
            yield line

    return StreamingResponse(log_generator(), media_type="text/plain")


# ---------------------------------------------------------------------------
# Deforestation proxy endpoints
# ---------------------------------------------------------------------------

@router.post("/api/deforestation/generate-template")
async def deforestation_generate_template(body: dict = Body(...)):
    base_url = body.get("baseUrl", "").rstrip("/")
    token    = body.get("token", "")
    url = f"{base_url}/services/fileupload-service/api/bulk-downloads/template?feature=ONBOARD_FARMER_ASSET_FORM"
    try:
        resp = ext_requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        resp.raise_for_status()
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except ext_requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/deforestation/download-fallback-template")
async def deforestation_download_fallback_template(body: dict = Body(...)):
    base_url  = body.get("baseUrl", "").rstrip("/")
    token     = body.get("token", "")
    upload_id = body.get("uploadId", "")
    url = f"{base_url}/services/fileupload-service/api/bulk-downloads/mass-upload-fallback-template/{upload_id}"
    try:
        resp = ext_requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60, stream=True)
        resp.raise_for_status()

        def iter_content():
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        filename = f"fallback_OnboardFarmerAssetTemplate{upload_id}.xlsx"
        return StreamingResponse(
            iter_content(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ext_requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/deforestation/download-template")
async def deforestation_download_template(body: dict = Body(...)):
    base_url  = body.get("baseUrl", "").rstrip("/")
    token     = body.get("token", "")
    template_id   = body.get("id", "")
    template_name = body.get("name", "template")
    url = f"{base_url}/services/fileupload-service/api/bulk-downloads/mass-upload-template/{template_id}"
    try:
        resp = ext_requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60, stream=True)
        resp.raise_for_status()

        def iter_content():
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        filename = f"{template_name}.xlsx"
        return StreamingResponse(
            iter_content(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ext_requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Static / root
# ---------------------------------------------------------------------------

@router.get("/deforestation")
async def deforestation_page():
    """Serve the standalone deforestation page."""
    return FileResponse("static/deforestation.html")


@router.get("/translation")
async def translation_page():
    """Serve the standalone translation page."""
    return FileResponse("static/translation.html")

@router.get("/housekeeping")
async def housekeeping_page():
    """Serve the standalone house keeping page."""
    return FileResponse("static/housekeeping.html")


@router.get("/update-phone")
async def update_phone_page():
    """Serve the standalone update phone number page."""
    return FileResponse("static/update_phone.html")


@router.get("/location-check")
async def location_check_page():
    """Serve the standalone location check page."""
    return FileResponse("static/location_check.html")


@router.get("/api/location-check/template")
async def download_location_check_template(format: str = "xlsx"):
    """Download the Location Check template as XLSX or CSV."""
    template_path = os.path.join(TEMPLATES_DIR, "Location_Check_Template.xlsx")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="Template not found")

    if format.lower() == "csv":
        import io
        import pandas as pd
        df = pd.read_excel(template_path)
        stream = io.StringIO()
        df.to_csv(stream, index=False)
        from fastapi.responses import Response
        return Response(
            content=stream.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="Location_Check_Template.csv"'}
        )

    return FileResponse(
        template_path,
        filename="Location_Check_Template.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Location_Check_Template.xlsx"'}
    )


class LocationItem(BaseModel):
    name: str
    latitude: float
    longitude: float

class CreateTemplateRequest(BaseModel):
    locations: list[LocationItem]
    filename: str = "Custom_Location_Template.xlsx"

@router.post("/api/location-check/create-template")
async def create_location_check_template(payload: CreateTemplateRequest):
    """Dynamically generate a custom Location Check Excel file from user-supplied locations."""
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Locations"

    headers = ["Location Name", "Latitude", "Longitude"]
    ws.append(headers)

    header_fill = PatternFill(start_color="009ADE", end_color="009ADE", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="E0E0E0"),
        right=Side(style="thin", color="E0E0E0"),
        top=Side(style="thin", color="E0E0E0"),
        bottom=Side(style="thin", color="E0E0E0")
    )

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    for loc in payload.locations:
        ws.append([loc.name, loc.latitude, loc.longitude])

    for row in ws.iter_rows(min_row=2, max_row=len(payload.locations) + 1):
        row[0].alignment = left_align
        row[1].alignment = center_align
        row[2].alignment = center_align
        for cell in row:
            cell.border = thin_border
            cell.font = Font(name="Calibri", size=11)

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = payload.filename if payload.filename.endswith(".xlsx") else f"{payload.filename}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/api/location-check/parse")
async def parse_location_file(file: UploadFile = File(...)):
    """Parse and validate uploaded location files (Excel or CSV)."""
    import io
    import pandas as pd
    import re

    def parse_single_coord(coord_str, is_lat=None):
        if coord_str is None or pd.isna(coord_str):
            return None
        s = str(coord_str).strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            pass

        is_neg = False
        if s.startswith('-'):
            is_neg = True
            s = s[1:].strip()

        su = s.upper()
        if is_lat is True:
            if 'SOUTH' in su or re.search(r'(?:[\d\.\'\"°]|\b)S\b', su) or su.endswith('S'):
                is_neg = True
            elif 'NORTH' in su or re.search(r'(?:[\d\.\'\"°]|\b)N\b', su) or su.endswith('N'):
                is_neg = False
        elif is_lat is False:
            if 'WEST' in su or re.search(r'(?:[\d\.\'\"°s]|\b)W\b', su) or su.endswith('W'):
                is_neg = True
            elif 'EAST' in su or re.search(r'(?:[\d\.\'\"°s]|\b)E\b', su) or su.endswith('E'):
                is_neg = False
        else:
            if 'SOUTH' in su or 'WEST' in su or su.endswith('S') or su.endswith('W'):
                is_neg = True

        cleaned = re.sub(r'[^\d\.]+', ' ', s).strip()
        parts = [float(p) for p in cleaned.split() if p]
        if not parts:
            return None
        if len(parts) == 1:
            val = parts[0]
        elif len(parts) == 2:
            val = parts[0] + parts[1] / 60.0
        elif len(parts) >= 3:
            val = parts[0] + parts[1] / 60.0 + parts[2] / 3600.0
        else:
            return None
        return -val if is_neg else val

    def parse_combined_coords(val_str):
        if val_str is None or pd.isna(val_str):
            return None, None
        s = str(val_str).strip()
        for delim in [',', ';', '/']:
            if delim in s:
                p = s.split(delim, 1)
                lat = parse_single_coord(p[0], True)
                lng = parse_single_coord(p[1], False)
                if lat is not None and lng is not None:
                    return lat, lng
        # Space separated with directional letters
        match = re.search(r'([0-9\.\s°\'\"d]+[NSns])\s*[,;]?\s*([0-9\.\s°\'\"d]+[EWew])', s)
        if match:
            lat = parse_single_coord(match.group(1), True)
            lng = parse_single_coord(match.group(2), False)
            if lat is not None and lng is not None:
                return lat, lng
        # Space separated numbers (e.g. 12.971598 77.594566)
        parts = s.split()
        if len(parts) == 2:
            lat = parse_single_coord(parts[0], True)
            lng = parse_single_coord(parts[1], False)
            if lat is not None and lng is not None:
                return lat, lng
        return None, None

    try:
        contents = await file.read()
        filename_lower = file.filename.lower()
        if filename_lower.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        elif filename_lower.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload .xlsx, .xls, or .csv")

        # Flexible column matching
        name_col = None
        lat_col = None
        lon_col = None
        pair_col = None

        for col in df.columns:
            c = str(col).strip().lower()
            if not name_col and c in ["location name", "location", "location_name", "locationname", "name", "plot", "plot name", "plot_name", "place", "title", "site", "farm", "field"]:
                name_col = col
            elif not lat_col and c in ["latitude", "lat", "latitude (dd)", "lat_dd", "y"]:
                lat_col = col
            elif not lon_col and c in ["longitude", "long", "lng", "lon", "longitude (dd)", "lon_dd", "x"]:
                lon_col = col
            elif not pair_col and c in ["coordinates", "coord", "coords", "latlong", "lat_long", "lat, long", "lat long", "gps", "geolocation"]:
                pair_col = col

        if (not lat_col or not lon_col) and not pair_col:
            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "error": f"Missing Latitude/Longitude or Coordinates columns. Found columns: {list(df.columns)}. Expected: 'Location Name', 'Latitude', 'Longitude' or 'Coordinates'."
                }
            )

        valid_locations = []
        invalid_rows = []

        for idx, row in df.iterrows():
            row_num = idx + 2
            loc_name = str(row[name_col]).strip() if (name_col and pd.notna(row[name_col])) else f"Location {idx + 1}"

            lat = None
            lon = None

            if lat_col and lon_col:
                raw_lat = row[lat_col]
                raw_lon = row[lon_col]
                lat = parse_single_coord(raw_lat, is_lat=True)
                lon = parse_single_coord(raw_lon, is_lat=False)
            elif pair_col:
                raw_pair = row[pair_col]
                lat, lon = parse_combined_coords(raw_pair)

            if lat is None or lon is None:
                invalid_rows.append({"row": row_num, "name": loc_name, "error": f"Could not parse valid coordinates from row {row_num}"})
                continue

            if not (-90.0 <= lat <= 90.0):
                invalid_rows.append({"row": row_num, "name": loc_name, "error": f"Latitude {lat} out of range (-90 to 90)"})
                continue
            if not (-180.0 <= lon <= 180.0):
                invalid_rows.append({"row": row_num, "name": loc_name, "error": f"Longitude {lon} out of range (-180 to 180)"})
                continue

            valid_locations.append({
                "id": idx + 1,
                "row": row_num,
                "name": loc_name,
                "lat": float(lat),
                "lng": float(lon),
                "raw_lat": str(row[lat_col]).strip() if (lat_col and pd.notna(row.get(lat_col))) else str(lat),
                "raw_lng": str(row[lon_col]).strip() if (lon_col and pd.notna(row.get(lon_col))) else str(lon),
                "status": "Original"
            })

        return {
            "success": True,
            "filename": file.filename,
            "total_rows": len(df),
            "valid_count": len(valid_locations),
            "invalid_count": len(invalid_rows),
            "locations": valid_locations,
            "invalid_rows": invalid_rows
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse file: {str(e)}")



class PasswordAutomationRequest(BaseModel):
    admin_username: str
    admin_password: str
    new_password: str
    tenant: str
    contact_number: str

@router.post("/api/change-password-automation")
async def change_password_automation(req: PasswordAutomationRequest):
    from app.automation import change_password_via_portal
    from fastapi.responses import StreamingResponse
    import asyncio
    import json
    
    queue = asyncio.Queue()

    async def on_update(msg):
        await queue.put({"status": "progress", "message": msg})

    async def run_automation():
        try:
            result = await change_password_via_portal(
                admin_username=req.admin_username,
                admin_password=req.admin_password,
                new_password=req.new_password,
                tenant=req.tenant,
                contact_number=req.contact_number,
                update_callback=on_update
            )
            await queue.put(result)
        except Exception as e:
            await queue.put({"status": "error", "message": str(e)})

    asyncio.create_task(run_automation())

    async def event_generator():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("status") in ["success", "error"]:
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")




@router.head("/")
@router.get("/")
async def read_root():
    """Serve the main single-page application."""
    return FileResponse("static/index.html")
