import time
import requests
import subprocess
import os
import schedule
import sys
import datetime
import socket

def safe_log_print(*args, **kwargs):
    msg = " ".join(str(a) for a in args)
    # Output to standard console (in case it's run manually)
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()
    
    # Append to server.log safely (opens and closes to avoid locking it permanently)
    try:
        with open("server.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        # Ignore errors if the file is locked for a split second by the main server
        pass

# Override print to ensure all existing print statements go to the logger
print = safe_log_print


STATUS_URL = "http://127.0.0.1:4444/api/server/status"
SHUTDOWN_URL = "http://127.0.0.1:4444/api/server/shutdown"
SERVER_PORT = 4444
SERVER_STARTUP_TIMEOUT = 120  # Max seconds to wait for server to come up


def wait_for_server(port=SERVER_PORT, timeout=SERVER_STARTUP_TIMEOUT):
    """Poll port until server is listening or timeout (seconds) is reached."""
    print(f"Waiting for server to come up on port {port} (max {timeout}s)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                print(f"Server is UP on port {port}. Proceeding.")
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(2)
    print(f"WARNING: Server did not come up within {timeout}s. Launching ngrok anyway.")
    return False


def execute_update_process():
    print("--------------------------------------------------")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Executing Daily Update Process...")
    
    # 1. Fetch the latest deployment.config from Git FIRST
    try:
        print("Fetching latest deployment.config from repository...")
        subprocess.check_call(["git", "fetch", "origin", "main"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.check_call(["git", "checkout", "origin/main", "--", "deployment.config"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Read the file
        deploy_to_production = False
        if os.path.exists("deployment.config"):
            with open("deployment.config", "r", encoding="utf-8") as f:
                content = f.read()
                if "deploy_to_production = True" in content or "deploy_to_production=True" in content.replace(" ", ""):
                    deploy_to_production = True
                    
        if not deploy_to_production:
            print("Action Denied: deploy_to_production is set to False in deployment.config.")
            print("Aborting daily update cycle.")
            print("--------------------------------------------------")
            return
            
        print("Deployment check passed. Checking for new changes in Git...")
        local_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
        remote_hash = subprocess.check_output(["git", "rev-parse", "origin/main"]).decode("utf-8").strip()
        
        if local_hash == remote_hash:
            print("No new changes found in Git. Local branch is up to date.")
            print("Aborting daily update cycle to prevent unnecessary restarts.")
            print("--------------------------------------------------")
            return
            
        print(f"New changes found (Local: {local_hash[:7]} -> Remote: {remote_hash[:7]}). Proceeding with update...")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to fetch deployment.config from Git. Code: {e.returncode}. Aborting.")
        return
    except Exception as e:
        print(f"ERROR reading deployment.config: {str(e)}. Aborting.")
        return

    # 2. Wait until no scripts are running
    while True:
        try:
            response = requests.get(STATUS_URL, timeout=10)
            if response.status_code == 200:
                active_jobs = response.json().get("active_jobs", 0)
                if active_jobs == 0:
                    print(f"[{time.strftime('%H:%M:%S')}] No active jobs running. Safe to proceed with update.")
                    break
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] Wait: {active_jobs} jobs are currently running. Checking again in 30 minutes...")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] Warning: Server returned status {response.status_code}. Is it running?")
                break
        except requests.exceptions.ConnectionError:
            print(f"[{time.strftime('%H:%M:%S')}] Server is currently offline. Proceeding to update anyway.")
            break
            
        time.sleep(30 * 60) # Wait 30 minutes (1800 seconds) before checking again

    # 3. Pull the latest code from Git
    try:
        print("Pulling latest changes from Git (origin main)...")
        subprocess.check_call(["git", "fetch", "origin", "main"])
        
        import shutil
        backup_file = "scheduled_jobs.json.bak"
        if os.path.exists("scheduled_jobs.json"):
            shutil.copy2("scheduled_jobs.json", backup_file)
            print("scheduled_jobs.json backed up.")
            
        subprocess.check_call(["git", "reset", "--hard", "origin/main"])
        
        if os.path.exists(backup_file):
            shutil.copy2(backup_file, "scheduled_jobs.json")
            os.remove(backup_file)
            print("scheduled_jobs.json restored.")
            
        print("Git pull successful!")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Git pull failed with code {e.returncode}. Aborting update.")
        return

    # 4. Stop the Server gracefully via API first
    print("Initiating Server Shutdown via API...")
    try:
        requests.post(SHUTDOWN_URL, timeout=5)
        print("Server shutdown signal sent successfully.")
    except requests.exceptions.ConnectionError:
        print("Server is already offline, no need to shut down.")

    # Give it a moment to process the API call
    time.sleep(3)

    # 5. Kill ALL old processes (server + ngrok + terminals) BEFORE starting anything new.
    #    This prevents the new CROPIN_SERVER window from being killed by a later taskkill.
    print("Killing all old server, ngrok processes and their terminal windows...")
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
            print(f"PowerShell cleanup warning: {ps_err}. Falling back to standard taskkill...")
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

        print("All old server/ngrok processes and terminal windows killed.")
    except Exception as e:
        print(f"Error during cleanup of old processes: {e}")

    # 6. Wait for OS to fully release port 4444
    print("Waiting for OS to release port 4444...")
    time.sleep(5)

    # 7. Start the new Server in a NEW visible terminal
    print("Starting Server via run_server.bat...")
    try:
        start_bat = os.path.abspath(os.path.join("batch_scripts", "run_server.bat"))
        if os.path.exists(start_bat):
            subprocess.Popen(f'"{start_bat}" --no-pause', shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
            print("run_server.bat launched successfully.")
        else:
            print(f"ERROR: Could not find {start_bat}")
    except Exception as e:
        print(f"ERROR running run_server.bat: {e}")

    # 8. CRITICAL: Wait until the server is actually listening on port 4444
    #    before starting ngrok. This is what caused ERR_NGROK_8012 —
    #    ngrok was starting while server was still running pip install / booting.
    wait_for_server(port=SERVER_PORT, timeout=SERVER_STARTUP_TIMEOUT)

    # 9. Start Ngrok ONLY AFTER the server is confirmed up
    print("Starting Ngrok tunnel...")
    try:
        ngrok_bat = os.path.abspath(os.path.join("batch_scripts", "run_ngrok.bat"))
        if os.path.exists(ngrok_bat):
            subprocess.Popen(f'"{ngrok_bat}" --no-pause', shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
            print("Ngrok restarted successfully.")
        else:
            print(f"ERROR: Could not find {ngrok_bat}")
    except Exception as e:
        print(f"ERROR restarting Ngrok: {e}")

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Update Process Finished.")
    print("--------------------------------------------------")

    # CRITICAL: Because run_server.bat automatically launches a NEW auto_update.py background task,
    # this current background process must terminate itself to avoid multiplying exponentially over time.
    print("Handing off the baton to the new instance. Exiting current updater process.")
    os._exit(0)

def main_loop():
    print("Auto-updater started. Scheduled to run daily at 00:00 (12:00 AM).")
    
    # Schedule to run every day at Midnight (12:00 AM)
    schedule.every().day.at("00:00").do(execute_update_process)
    
    while True:
        schedule.run_pending()
        time.sleep(60) # Check planner once a minute

if __name__ == "__main__":
    main_loop()
