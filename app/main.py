from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
import shutil
import os
import importlib.util
from typing import List, Dict
import json
from app.core.auth import get_access_token
from openpyxl import load_workbook
from openpyxl.worksheet.datavalidation import DataValidation
import pandas as pd
import asyncio
import ast

from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

# ... existing imports ...


# ... existing imports ...

SCRIPTS_DIR = "app/scripts"
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Clean up temporary directories
    print("Execute Clean up temporary directories...")
    dirs_to_clean = [UPLOAD_DIR, OUTPUT_DIR]
    for d in dirs_to_clean:
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
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")



# SSE Connection Manager
class ConnectionManager:
    def __init__(self):
        # Map client_id -> asyncio.Queue (for live streaming)
        self.active_connections: Dict[str, asyncio.Queue] = {}
        # Map client_id -> List[str] (for history/replay)
        self.client_logs: Dict[str, List[str]] = {}
        # Set of client_ids with active running tasks
        self.active_tasks: set = set()
        # Set of client_ids that requested cancellation
        self.cancellation_requests: set = set()

    def mark_active(self, client_id: str):
        self.active_tasks.add(client_id)
        # Ensure no pending cancel request from previous run
        if client_id in self.cancellation_requests:
            self.cancellation_requests.remove(client_id)

    def mark_inactive(self, client_id: str):
        if client_id in self.active_tasks:
            self.active_tasks.remove(client_id)
        if client_id in self.cancellation_requests:
            self.cancellation_requests.remove(client_id)

    def request_cancel(self, client_id: str):
        self.cancellation_requests.add(client_id)

    def is_cancelled(self, client_id: str) -> bool:
        return client_id in self.cancellation_requests

    def is_active(self, client_id: str) -> bool:
        return client_id in self.active_tasks

    def clear_logs(self, client_id: str):
        self.client_logs[client_id] = []

    async def connect(self, client_id: str):
        self.active_connections[client_id] = asyncio.Queue()
        print(f"Client {client_id} connected for SSE.")
        
        # Replay history immediately upon connection
        if client_id in self.client_logs and self.client_logs[client_id]:
            await self.active_connections[client_id].put("Connected to server (SSE) - Resuming session...")
            for message in self.client_logs[client_id]:
                await self.active_connections[client_id].put(message)
        else:
             self.client_logs[client_id] = []
             await self.active_connections[client_id].put("Connected to server (SSE).")

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            print(f"Client {client_id} disconnected.")

    async def send_log(self, message: str, client_id: str):
        # 1. Archive
        if client_id not in self.client_logs:
            self.client_logs[client_id] = []
        self.client_logs[client_id].append(message)
        
        # 2. Stream if active
        if client_id in self.active_connections:
            await self.active_connections[client_id].put(message)

    async def stream_logs(self, client_id: str):
        try:
            queue = self.active_connections[client_id]
            while True:
                # Wait for message
                message = await queue.get()
                # Format as SSE event
                yield f"data: {message}\n\n"
        except asyncio.CancelledError:
            self.disconnect(client_id)
            print(f"Stream cancelled for {client_id}")

manager = ConnectionManager()

@app.get("/api/logs/{client_id}")
async def sse_endpoint(client_id: str):
    await manager.connect(client_id)
    return StreamingResponse(manager.stream_logs(client_id), media_type="text/event-stream")

@app.get("/api/status/{client_id}")
async def get_task_status(client_id: str):
    return {"is_running": manager.is_active(client_id)}

@app.post("/api/clear_session/{client_id}")
async def clear_session(client_id: str):
    manager.clear_logs(client_id)
    manager.mark_inactive(client_id)
    return {"status": "cleared"}

@app.post("/api/stop/{client_id}")
async def stop_execution(client_id: str):
    if manager.is_active(client_id):
        manager.request_cancel(client_id)
        return {"status": "stopping", "message": "Stop requested. Process will terminate shortly."}
    return {"status": "ignored", "message": "No active process found."}

@app.get("/")
async def read_root():
    return FileResponse("static/index.html")

@app.get("/api/scripts")
async def list_scripts():
    scripts = []
    # Define default Configs (URL + Label + Input Requirement)
    default_configs = {
        "AddTagsWithNewAPI.py": {
            "url": "https://cloud.cropin.in/services/master/api/tags",
            "label": "Post Api Url",
            "requires_input": True
        },
        "Update_Farmer_Details.py": {
            "url": "https://cloud.cropin.in/services/farm/api/farmers",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Update_Asset_Details.py": {
            "url": "https://cloud.cropin.in/services/farm/api/assets",
            "label": "Base Api Url",
            "requires_input": True
        },
        "PR_Enablement.py": {
            "url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
            "label": "Base Api Url",
            "requires_input": True
        },
        "PR_and_Weather_Enablement.py": {
            "url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
            "label": "Base Api Url",
            "requires_input": True
        },
        "RefreshPlans.py": {
            "url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
            "label": "Base Api Url (Fixed in Script)",
            "requires_input": True
        },
        "Update_Asset_Additional_Attribute.py": {
            "url": "https://cloud.cropin.in/services/farm/api/assets",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Update_Farmer_Additional_Attribute.py": {
            "url": "https://cloud.cropin.in/services/farm/api/farmers",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Add_Users.py": {
            "url": "https://cloud.cropin.in/services/user/api/users/images",
            "label": "User API Url",
            "requires_input": True
        },
        "Area_Audit_Removal.py": {
            "url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Update_Farmer_Tags.py": {
            "url": "https://cloud.cropin.in/services/farm/api/farmers",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Update_Asset_Tags.py": {
            "url": "https://cloud.cropin.in/services/farm/api/assets",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Update_Farmer_Address.py": {
            "url": "https://cloud.cropin.in/services/farm/api/farmers",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Update_Asset_Address.py": {
            "url": "https://cloud.cropin.in/services/farm/api/assets",
            "label": "Base Api Url",
            "requires_input": True
        },
        "PR_Enablement_Bulk.py": {
            "url": "https://cloud.cropin.in/services/farm/api/croppable-areas/plot-risk/batch",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Edit_Plans_in_Variety_with_or_without_recurring.py": {
            "url": "https://cloud.cropin.in/services/farm/api/plans",
            "label": "Plan API URL",
            "requires_input": True
        },
        "Area_Audit_To_CA.py": {
            "url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
            "label": "Croppable Area API URL",
            "requires_input": True
        },
        "Add_Cropstages_to_Variety.py": {
            "url": "https://cloud.cropin.in/services/farm/api/varieties",
            "label": "Variety API URL",
            "url2": "https://cloud.cropin.in/services/farm/api/crop-stages",
            "label2": "Crop Stage API URL",
            "requires_input": True
        },
        "Add_Seed_Grades_to_Variety.py": {
            "url": "https://cloud.cropin.in/services/farm/api/varieties",
            "label": "Variety API URL",
            "url2": "https://cloud.cropin.in/services/farm/api/seed-grades",
            "label2": "Seed Grade API URL",
            "requires_input": True
        },
        "Add_Varieties_or_Sub_Varieties.py": {
            "url": "https://cloud.cropin.in/services/farm/api/varieties",
            "label": "Variety API URL",
            "requires_input": True
        },
        "Split_CAs.py": {
            "url": "https://cloud.cropin.in/services/farm/api/projects",
            "label": "Base API URL",
            "requires_input": True
        },
        "Enable_Cropin_Connect.py": {
            "url": "https://cloud.cropin.in/services/farm/api/acresquare/farmers-enable",
            "label": "Enablement API URL",
            "requires_input": True
        },
        "Delete_Users.py": {
            "url": "https://cloud.cropin.in/services/user/api/users/bulk",
            "label": "Delete API URL",
            "requires_input": True
        },
        "Enable_Or_Disable_User.py": {
            "url": "https://cloud.cropin.in/services/user/api/users",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Bulk_Delete_Farmers.py": {
            "url": "https://cloud.cropin.in/services/farm/api/farmers/bulk",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Bulk_Delete_Assets.py": {
            "url": "https://cloud.cropin.in/services/farm/api/assets/bulk",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Update_DOS_Variety_to_CA.py": {
            "url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Farmer_Refresh_EditandSave.py": {
            "url": "https://cloud.cropin.in/services/farm/api/farmers",
            "label": "Base Api Url",
            "requires_input": True
        },
        "Asset_Refresh_EditandSave.py": {
            "url": "https://cloud.cropin.in/services/farm/api/assets",
            "label": "Base Api Url",
            "requires_input": True
        }
    }
    
    for filename in os.listdir(SCRIPTS_DIR):
        if filename.endswith(".py") and filename != "__init__.py":
            # Extract docstring for details
            filepath = os.path.join(SCRIPTS_DIR, filename)
            description = "No description available."
            input_description = "Standard Excel Input."
            
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    file_content = f.read()
                    tree = ast.parse(file_content)
                    docstring = ast.get_docstring(tree)
                    
                    if docstring:
                        # Split by "Inputs:" to separate description and input details
                        parts = docstring.split("Inputs:")
                        description = parts[0].strip()
                        if len(parts) > 1:
                            input_description = parts[1].strip()
            except Exception as e:
                print(f"Error parsing docstring for {filename}: {e}")

            config = default_configs.get(filename, {
                "url": "https://cloud.cropin.in/services/master/api", 
                "label": "Api Url",
                "requires_input": True
            })
            scripts.append({
                "name": filename, 
                "url": config["url"],
                "label": config["label"],
                "url2": config.get("url2"),
                "label2": config.get("label2"),
                "requires_input": config.get("requires_input", True),
                "description": description,
                "input_description": input_description
            })
    
    # Sort scripts alphabetically by name
    scripts.sort(key=lambda x: x['name'])
            
    return {"scripts": scripts}

@app.get("/api/template/{script_name}")
async def get_template(script_name: str):
    # Construct expected template filename
    # e.g. AddTagsWithNewAPI.py -> AddTagsWithNewAPI.xlsx
    template_filename = script_name.replace('.py', '.xlsx')
    template_path = os.path.join("sample_templates", template_filename)

    if os.path.exists(template_path):
        return FileResponse(template_path, filename=template_filename, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        # Fallback or error if template doesn't exist
        raise HTTPException(status_code=404, detail=f"Template not found for {script_name}. Please add {template_filename} to sample_templates folder.")

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    # Save uploaded file
    input_filename = f"input_{file.filename}"
    input_path = os.path.join(UPLOAD_DIR, input_filename)
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"filename": file.filename, "server_path": input_filename}

@app.get("/api/download/{filename}")
async def download_result(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    raise HTTPException(status_code=404, detail="File not found")

async def process_background_script(
    script_path: str,
    script_name: str,
    input_path: str,
    output_path: str,
    output_filename: str,
    config_dict: dict,
    client_id: str
):
    try:
        manager.mark_active(client_id)
        
        # AUTH LOGIC
        username = config_dict.get("username")
        password = config_dict.get("password")
        environment = config_dict.get("environment")
        tenant_code = config_dict.get("tenant_code")
        
        # Log Auth Start
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
        
        # Capture loop for threadsafe logging
        # Note: Since we are in async function, we can just use manager.send_log directly if we were running async.
        # But module.run is blocking, so we run it in a thread.
        # The log_callback needs to schedule the coroutine on the loop.
        
        loop = asyncio.get_running_loop()

        # Define Log Callback
        def log_callback(message):
            # Check for cancellation
            # print(f"DEBUG: Checking cancellation for {client_id}. Cancelled: {manager.is_cancelled(client_id)}. Msg: {message[:20]}") 
            if manager.is_cancelled(client_id):
                print(f"DEBUG: Raising Stop Exception for {client_id}")
                raise Exception("Job Stopped by User")

            try:
               asyncio.run_coroutine_threadsafe(manager.send_log(message, client_id), loop)
            except Exception as e:
               print(f"Log Error: {e}")

        # Load script module dynamically
        spec = importlib.util.spec_from_file_location("module.name", script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if hasattr(module, "run"):
            await manager.send_log(f"Starting execution of {script_name}...", client_id)
            
            # Wrapper to inject callback if supported
            def run_wrapper():
                # Check signature of run arguments
                import inspect
                sig = inspect.signature(module.run)
                if 'log_callback' in sig.parameters:
                     module.run(input_path, output_path, config_dict, log_callback=log_callback)
                else:
                     module.run(input_path, output_path, config_dict)

            await asyncio.to_thread(run_wrapper)
            
            await manager.send_log("Script execution finished.", client_id)
            
            if os.path.exists(output_path):
                # Signal completion with filename
                await manager.send_log(f"JOB_COMPLETED::{output_filename}", client_id)
            else:
                 await manager.send_log("JOB_FAILED::Execution finished but no output file was generated.", client_id)
        else:
            await manager.send_log("JOB_FAILED::Script does not have a 'run' function", client_id)

    except Exception as e:
        import traceback
        traceback.print_exc()
        await manager.send_log(f"JOB_FAILED::Error: {str(e)}", client_id)
    finally:
        manager.mark_inactive(client_id)


@app.post("/api/execute")
async def execute_script(
    background_tasks: BackgroundTasks,
    script_name: str = Form(...),
    input_filename: str = Form(None), # Optional now
    config: str = Form(...),
    client_id: str = Form(...) # To send logs to the right client
):
    # Clear previous logs for this client since it's a new run
    manager.clear_logs(client_id)

    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="Script not found")

    input_path = None
    output_filename = f"{script_name.replace('.py', '')}_Output.xlsx"
    
    if input_filename:
        input_path = os.path.join(UPLOAD_DIR, f"input_{input_filename}")
        if not os.path.exists(input_path):
            raise HTTPException(status_code=404, detail="Input file not found")
        
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    try:
        config_dict = json.loads(config)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid config JSON")

    # Add to background tasks
    background_tasks.add_task(
        process_background_script,
        script_path,
        script_name,
        input_path,
        output_path,
        output_filename,
        config_dict,
        client_id
    )
    
    return {"status": "queued", "message": "Script execution started in background"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=4444)
