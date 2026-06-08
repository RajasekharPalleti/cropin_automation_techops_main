import time
import requests
import subprocess
import os
import sys
import socket

# Standalone force restart script
# Mirrors the restart logic from auto_update.py but without the Git pull.

SHUTDOWN_URL = "http://127.0.0.1:4444/api/server/shutdown"
SAFE_LOG_FILE = "server.log"
SERVER_PORT = 4444
SERVER_STARTUP_TIMEOUT = 120  # Max seconds to wait for server to come up

def safe_log_print(*args):
    msg = " ".join(str(a) for a in args)
    # Output to standard console
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()
    # Append to server.log safely
    try:
        with open(SAFE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ForceRestart] " + msg + "\n")
    except Exception:
        pass

def wait_for_server(port=SERVER_PORT, timeout=SERVER_STARTUP_TIMEOUT):
    """Poll port until server is listening or timeout (seconds) is reached."""
    safe_log_print(f"Waiting for server to come up on port {port} (max {timeout}s)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                safe_log_print(f"Server is UP on port {port}. Proceeding.")
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(2)
    safe_log_print(f"WARNING: Server did not come up within {timeout}s. Launching ngrok anyway.")
    return False

def execute_force_restart():
    safe_log_print("--------------------------------------------------")
    safe_log_print("Executing Force Update/Restart Process (Manual Trigger)...")
    
    # 0. Git Pull (same as auto_update.py but without safety checks)
    try:
        safe_log_print("Fetching latest changes from repository...")
        subprocess.check_call(["git", "fetch", "origin", "main"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        import shutil
        backup_file = "scheduled_jobs.json.bak"
        if os.path.exists("scheduled_jobs.json"):
            shutil.copy2("scheduled_jobs.json", backup_file)
            safe_log_print("scheduled_jobs.json backed up.")
            
        # Hard reset to pull everything (ignoring deployment.config for manual force)
        safe_log_print("Pulling latest code (reset --hard)...")
        subprocess.check_call(["git", "reset", "--hard", "origin/main"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(backup_file):
            shutil.copy2(backup_file, "scheduled_jobs.json")
            os.remove(backup_file)
            safe_log_print("scheduled_jobs.json restored.")
            
        safe_log_print("Git update successful.")
        
    except Exception as e:
        safe_log_print(f"ERROR during Git update: {e}. Proceeding with restart only.")
    
    # 1. Stop the Server gracefully via API first
    safe_log_print("Initiating Server Shutdown via API...")
    try:
        requests.post(SHUTDOWN_URL, timeout=5)
        safe_log_print("Server shutdown signal sent successfully.")
    except Exception as e:
        safe_log_print(f"Warning: API shutdown signal failed (Server might be hung): {e}")
    
    # Give it a moment to process the API call
    time.sleep(3)
    
    # 2. Kill ALL old processes (server + ngrok + terminals) BEFORE starting anything new.
    #    This prevents the new CROPIN_SERVER window from being killed by a later taskkill.
    safe_log_print("Killing all old server, ngrok processes and their terminal windows...")
    try:
        # Kill the process listening on port 4444
        stop_bat = os.path.abspath(os.path.join("batch_scripts", "stop_server.bat"))
        if os.path.exists(stop_bat):
            subprocess.call(f'echo. | "{stop_bat}"', shell=True)
        
        # Kill ngrok process
        subprocess.call(["taskkill", "/IM", "ngrok.exe", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Kill old CMD windows by title (only OLD ones — new ones haven't been created yet)
        # We query for PIDs of cmd windows containing any batch script title keywords
        try:
            ps_command = (
                "Get-Process -Name cmd -ErrorAction SilentlyContinue | "
                "Where-Object { $_.MainWindowTitle -like '*cropin*' -or "
                "$_.MainWindowTitle -like '*restart_server*' -or "
                "$_.MainWindowTitle -like '*restart_ngrok*' -or "
                "$_.MainWindowTitle -like '*stop_server*' -or "
                "$_.MainWindowTitle -like '*stop_ngrok*' } | "
                "Select-Object -ExpandProperty Id"
            )
            output = subprocess.check_output(["powershell", "-Command", ps_command]).decode("utf-8").strip()
            if output:
                pids = [p.strip() for p in output.split("\n") if p.strip()]
                for pid in pids:
                    if pid:
                        subprocess.call(["taskkill", "/F", "/PID", pid, "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as ps_err:
            safe_log_print(f"PowerShell cleanup warning: {ps_err}. Falling back to standard taskkill...")
            # Fallback
            subprocess.call(['taskkill', '/F', '/FI', 'WINDOWTITLE eq CROPIN_SERVER*',  '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.call(['taskkill', '/F', '/FI', 'WINDOWTITLE eq CROPIN_NGROK*',   '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.call(['taskkill', '/F', '/FI', 'WINDOWTITLE eq RESTART_SERVER*', '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.call(['taskkill', '/F', '/FI', 'WINDOWTITLE eq RESTART_NGROK*',  '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.call(['taskkill', '/F', '/FI', 'WINDOWTITLE eq STOP_SERVER*',    '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.call(['taskkill', '/F', '/FI', 'WINDOWTITLE eq STOP_NGROK*',     '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Kill any old auto_update.py background process to hand over the baton
        current_pid = os.getpid()
        try:
            ps_update_cmd = (
                f"Get-CimInstance Win32_Process -Filter \"Name = 'python.exe' and CommandLine like '%auto_update.py%'\" | "
                f"Where-Object {{ $_.ProcessId -ne {current_pid} }} | "
                f"Invoke-CimMethod -MethodName Terminate"
            )
            subprocess.call(["powershell", "-Command", ps_update_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            subprocess.call('wmic process where "commandline like \'%auto_update.py%\' and processid != ' + str(current_pid) + '" delete', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        safe_log_print("All old server/ngrok processes and terminal windows killed.")
    except Exception as e:
        safe_log_print(f"Error during cleanup of old processes: {e}")

    # 3. Wait for OS to fully release port 4444
    safe_log_print("Waiting for OS to release port 4444...")
    time.sleep(5)

    # 4. Start the new Server in a NEW visible terminal
    safe_log_print("Starting Server in NEW visible terminal...")
    try:
        start_bat = os.path.abspath(os.path.join("batch_scripts", "run_server.bat"))
        if os.path.exists(start_bat):
            subprocess.Popen(f'"{start_bat}" --no-pause', shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
            safe_log_print("run_server.bat launched in new window.")
        else:
            safe_log_print(f"ERROR: Could not find {start_bat}")
    except Exception as e:
        safe_log_print(f"ERROR starting Server: {e}")

    # 5. CRITICAL: Wait until the server is actually listening on port 4444
    #    before starting ngrok. This is what caused ERR_NGROK_8012 before —
    #    ngrok was starting while server was still running pip install / booting.
    wait_for_server(port=SERVER_PORT, timeout=SERVER_STARTUP_TIMEOUT)

    # 6. Start Ngrok ONLY AFTER the server is confirmed up
    safe_log_print("Starting Ngrok in NEW visible terminal...")
    try:
        ngrok_bat = os.path.abspath(os.path.join("batch_scripts", "run_ngrok.bat"))
        if os.path.exists(ngrok_bat):
            subprocess.Popen(f'"{ngrok_bat}" --no-pause', shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
            safe_log_print("Ngrok restarted in new window.")
        else:
            safe_log_print(f"ERROR: Could not find {ngrok_bat}")
    except Exception as e:
        safe_log_print(f"ERROR restarting Ngrok: {e}")
        
    safe_log_print("Force Restart Process Finished. Baton handed over to new instance.")
    safe_log_print("--------------------------------------------------")
    os._exit(0)

if __name__ == "__main__":
    execute_force_restart()
