import json
import os
import asyncio
import importlib.util
import traceback
from datetime import datetime, timedelta
import logging

from app.script_configs import SCRIPTS_DIR, OUTPUT_DIR
from app.core.auth import get_access_token
from app.state import backup_manager, manager, JobStoppedException

SCHEDULES_FILE = "scheduled_jobs.json"
logger = logging.getLogger(__name__)

def load_jobs():
    if not os.path.exists(SCHEDULES_FILE):
        return {}
    try:
        with open(SCHEDULES_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # File exists but is empty/corrupt
        return {}
    except Exception as e:
        logger.error(f"Error loading scheduled jobs: {e}")
        return {}

def save_jobs(jobs):
    try:
        with open(SCHEDULES_FILE, "w") as f:
            json.dump(jobs, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving scheduled jobs: {e}")

def mark_missed_jobs_on_startup():
    """
    Called once at server startup.
    Any job that is still 'pending' but whose run_time is already in the past
    is immediately marked 'missed' so it never runs silently late.
    """
    jobs = load_jobs()
    now = datetime.now()
    changed = False

    for job_id, data in jobs.items():
        if data.get("status") != "pending":
            continue
        try:
            run_dt = datetime.fromisoformat(data["run_time"])
            if now > run_dt:
                logger.warning(
                    f"[Startup] Job {job_id} ({data.get('script_name', '?')}) "
                    f"was scheduled for {data['run_time']} but was never executed "
                    "(server was down). Marking as 'missed'."
                )
                jobs[job_id]["status"] = "missed"
                jobs[job_id]["error"] = (
                    f"Job missed: server was offline during the scheduled window "
                    f"({data['run_time']})."
                )
                jobs[job_id]["completed_at"] = now.isoformat()
                changed = True
        except (ValueError, KeyError):
            pass  # Ignore malformed run_time entries

    if changed:
        save_jobs(jobs)
        logger.info("[Startup] Missed-job sweep complete.")


def _schedule_next_occurrence(parent_job_id: str, job_data: dict) -> None:
    """
    Creates a new pending job for the next daily or weekly run.
    Called after a recurring job completes (successfully or permanently failed).
    """
    import uuid
    recurrence = job_data.get("recurrence", "none")
    if not recurrence or recurrence == "none":
        return

    now = datetime.now()
    try:
        base_dt = datetime.fromisoformat(job_data["run_time"])
    except (ValueError, KeyError):
        base_dt = now

    if recurrence == "daily":
        next_dt = base_dt + timedelta(days=1)
        if next_dt <= now:          # catch-up guard
            next_dt = now + timedelta(days=1)
    elif recurrence == "weekly":
        next_dt = base_dt + timedelta(weeks=1)
        if next_dt <= now:
            next_dt = now + timedelta(weeks=1)
    else:
        return

    new_job_id = str(uuid.uuid4())
    new_job = {
        "job_id":      new_job_id,
        "script_name": job_data["script_name"],
        "run_time":    next_dt.strftime("%Y-%m-%dT%H:%M"),
        "status":      "pending",
        "created_at":  now.isoformat(),
        "config":      job_data["config"],
        "input_file":  job_data.get("input_file"),
        "recurrence":  recurrence,
        "max_retries": job_data.get("max_retries", 1),
        "retry_count": 0,
        "parent_job_id": parent_job_id,
    }
    jobs = load_jobs()
    jobs[new_job_id] = new_job
    save_jobs(jobs)
    logger.info(
        f"[Recurring] Next '{job_data['script_name']}' run queued for "
        f"{new_job['run_time']} (job {new_job_id[:8]})"
    )


async def process_scheduled_script(job_id: str, job_data: dict):
    """
    Runs a scheduled script entirely in the background, logging primarily 
    to standard output (server.log) instead of pushing SSE events.
    """
    script_name = job_data["script_name"]
    input_path = job_data.get("input_file")
    config_dict = job_data["config"]
    
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    
    output_filename = f"{os.path.splitext(os.path.basename(input_path))[0]}_Output.xlsx" if input_path else f"{script_name.replace('.py', '')}_Output.xlsx"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    logger.info(f"[{script_name}] Scheduled Job {job_id} starting...")

    # Update job state
    jobs = load_jobs()
    if job_id in jobs:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["started_at"] = datetime.now().isoformat()
        save_jobs(jobs)

    try:
        # --- Authentication ---
        username = config_dict.get("username")
        password = config_dict.get("password")
        environment = config_dict.get("environment")
        tenant_code = config_dict.get("tenant_code")

        if username and password and tenant_code:
            try:
                token = get_access_token(tenant_code, username, password, environment)
                if token:
                    config_dict["token"] = token
                else:
                    raise Exception("No token returned.")
            except Exception as auth_err:
                logger.error(f"[{script_name}] Auth failed: {auth_err}")
                raise

        # Silent log callback for thread progression logs
        # We do NOT log these because the scripts themselves already call `print()` natively,
        # which is captured into server.log by main.py! Logging here causes duplicate lines.
        def silent_log_callback(message):
            if manager.is_cancelled(job_id):
                raise JobStoppedException("Job Stopped by User")

        # --- Load Script ---
        if not os.path.exists(script_path):
            raise Exception(f"Script {script_name} not found.")

        spec = importlib.util.spec_from_file_location("module.name", script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "run"):
            # Inform the script what its client_id is so `manager.is_cancelled` works natively!
            config_dict["client_id"] = job_id
            manager.mark_active(job_id, None, script_name)

            def run_wrapper():
                import inspect
                sig = inspect.signature(module.run)
                if "log_callback" in sig.parameters:
                    module.run(input_path, output_path, config_dict, log_callback=silent_log_callback)
                else:
                    module.run(input_path, output_path, config_dict)

            try:
                await asyncio.to_thread(run_wrapper)
                
                if manager.is_cancelled(job_id):
                    logger.warning("scheduled run was forcefully terminated by the user.")
                else:
                    logger.info("scheduled run is complete please check the backup folder to see the output file.")

                # 1. Backup input file first (source of truth)
                if input_path and os.path.exists(input_path):
                    backup_manager.upload_file(input_path)

                # 2. Backup output file
                if os.path.exists(output_path):
                    backup_manager.upload_file(output_path)

            finally:
                manager.mark_inactive(job_id)

        else:
            raise Exception(f"Script {script_name} does not have a 'run' function.")

        # Mark as completed / handle recurrence
        if not manager.is_cancelled(job_id):
            jobs = load_jobs()
            if job_id in jobs:
                jobs[job_id]["status"] = "completed"
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
                save_jobs(jobs)
            # Queue next occurrence AFTER saving, so load_jobs gets a fresh copy
            _schedule_next_occurrence(job_id, job_data)

    except JobStoppedException:
        logger.warning(f"[{script_name}] Scheduled Job {job_id} was forcefully terminated by the user.")
    except Exception as e:
        logger.error(f"[{script_name}] Execution failed: {e}")
        logger.error(traceback.format_exc())

        jobs = load_jobs()
        if job_id in jobs:
            retry_count  = jobs[job_id].get("retry_count", 0)
            max_retries  = jobs[job_id].get("max_retries", 1)
            recurrence   = jobs[job_id].get("recurrence", "none")

            if retry_count < max_retries:
                # Re-queue same job for retry in 5 minutes
                next_run = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
                jobs[job_id]["status"]      = "pending"
                jobs[job_id]["retry_count"] = retry_count + 1
                jobs[job_id]["run_time"]    = next_run
                jobs[job_id]["last_error"]  = str(e)
                save_jobs(jobs)
                logger.warning(
                    f"[{script_name}] Retry {retry_count + 1}/{max_retries} "
                    f"scheduled for {next_run} (job {job_id[:8]})"
                )
            else:
                # Retries exhausted — mark permanently failed
                jobs[job_id]["status"]       = "failed"
                jobs[job_id]["error"]        = str(e)
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
                save_jobs(jobs)
                # Still queue next recurrence even if this run ultimately failed
                if recurrence and recurrence != "none":
                    _schedule_next_occurrence(job_id, jobs[job_id])


async def schedule_runner_task():
    """Poller loop running as a background asyncio task in main.py lifespan"""
    while True:
        try:
            now = datetime.now()
            jobs = load_jobs()
            to_run = []
            
            for j_id, data in jobs.items():
                if data["status"] == "pending":
                    # Parse run time "YYYY-MM-DDTHH:MM"
                    try:
                        run_dt = datetime.fromisoformat(data["run_time"])
                        if now >= run_dt:
                            to_run.append((j_id, data))
                    except ValueError:
                        pass # Ignore malformed dates
            
            for j_id, data in to_run:
                # Fire and forget
                asyncio.create_task(process_scheduled_script(j_id, data))
                
        except Exception as e:
            logger.error(f"Scheduler Poller Error: {e}")

        await asyncio.sleep(60) # Wait 1 minute before checking again
