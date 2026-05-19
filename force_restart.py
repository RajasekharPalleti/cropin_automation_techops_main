import time
import requests
import subprocess
import os
import sys

# Standalone force restart script
# Mirrors the restart logic from auto_update.py but without the Git pull.

SHUTDOWN_URL = "http://127.0.0.1:4444/api/server/shutdown"
SAFE_LOG_FILE = "server.log"

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
    
    # 1. Stop the Server (via API first for grace, then direct kill)
    safe_log_print("Initiating Server Shutdown via API...")
    try:
        requests.post(SHUTDOWN_URL, timeout=5)
        safe_log_print("Server shutdown signal sent successfully.")
    except Exception as e:
        safe_log_print(f"Warning: API shutdown signal failed (Server might be hung): {e}")
    
    # Give it a moment to process the API call, then ensure it's dead
    time.sleep(3)
    
    safe_log_print("Ensuring port 4444 is clear and closing old terminals/updaters...")
    try:
        # 1. Kill the process on 4444
        stop_bat = os.path.abspath(os.path.join("batch_scripts", "stop_server.bat"))
        if os.path.exists(stop_bat):
            subprocess.call(f'echo. | "{stop_bat}"', shell=True)
            
        # 2. Force kill the CMD window with CROPIN_SERVER title
        subprocess.call(['taskkill', '/F', '/FI', 'WINDOWTITLE eq CROPIN_SERVER*', '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 3. Kill any old auto_update.py background process to handover the baton
        # We use wmic to find processes with 'auto_update.py' in the command line
        subprocess.call('wmic process where "commandline like \'%auto_update.py%\'" delete', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        safe_log_print("Old server terminal and auto-updater killed.")
    except Exception as e:
        safe_log_print(f"Error clearing server port/terminal/updater: {e}")

    # Wait for OS to free the socket
    time.sleep(5)

    safe_log_print("Starting Server in NEW visible terminal...")
    try:
        start_bat = os.path.abspath(os.path.join("batch_scripts", "run_server.bat"))
        if os.path.exists(start_bat):
            # Using 'start' is the most robust way to get a new visible window on Windows
            subprocess.Popen(f'start cmd /c "{start_bat}" --no-pause', shell=True)
            safe_log_print("run_server.bat launched in new window.")
        else:
            safe_log_print(f"ERROR: Could not find {start_bat}")
    except Exception as e:
        safe_log_print(f"ERROR starting Server: {e}")
        
    safe_log_print("Force killing ngrok and old cmd tabs...")
    subprocess.call(["taskkill", "/IM", "ngrok.exe", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.call(['taskkill', '/F', '/FI', 'WINDOWTITLE eq CROPIN_NGROK*', '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Force close the old cmd.exe tabs to prevent accumulation using exact window titles
    subprocess.call(['taskkill', '/F', '/FI', 'WINDOWTITLE eq CROPIN_SERVER*', '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.call(['taskkill', '/F', '/FI', 'WINDOWTITLE eq CROPIN_NGROK*', '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.call(['taskkill', '/F', '/FI', 'WINDOWTITLE eq RESTART_SERVER*', '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.call(['taskkill', '/F', '/FI', 'WINDOWTITLE eq RESTART_NGROK*', '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    time.sleep(5)

    safe_log_print("Starting Ngrok in NEW visible terminal...")
    try:
        ngrok_bat = os.path.abspath(os.path.join("batch_scripts", "run_ngrok.bat"))
        if os.path.exists(ngrok_bat):
            subprocess.Popen(f'start cmd /c "{ngrok_bat}" --no-pause', shell=True)
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
