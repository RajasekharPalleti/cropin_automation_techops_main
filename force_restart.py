import time
import requests
import subprocess
import os
import sys
import socket

# Standalone force restart script
# Mirrors the restart logic from auto_update.py but without the Git pull.

def get_server_port():
    try:
        with open("app/script_configs.py", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("SERVER_PORT"):
                    return int(line.split("=")[1].strip())
    except Exception:
        pass
    return 4444

SERVER_PORT = get_server_port()
SHUTDOWN_URL = f"http://127.0.0.1:{SERVER_PORT}/api/server/shutdown"
SAFE_LOG_FILE = "server.log"
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
            
        config_file = "json_config/weekly_report_config.json"
        config_backup = "weekly_report_config.json.bak"
        if os.path.exists(config_file):
            shutil.copy2(config_file, config_backup)
            safe_log_print(f"{config_file} backed up.")
            
        # Hard reset to pull everything (ignoring deployment.config for manual force)
        safe_log_print("Pulling latest code (reset --hard)...")
        subprocess.check_call(["git", "reset", "--hard", "origin/main"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(backup_file):
            shutil.copy2(backup_file, "scheduled_jobs.json")
            os.remove(backup_file)
            safe_log_print("scheduled_jobs.json restored.")
            
        if os.path.exists(config_backup):
            if not os.path.exists("json_config"):
                os.makedirs("json_config")
            shutil.copy2(config_backup, config_file)
            os.remove(config_backup)
            safe_log_print(f"{config_file} restored.")
            
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
    is_windows = os.name == 'nt'
    try:
        if is_windows:
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
                    "Select-Object -ExpandProperty Id; exit 0"
                )
                output = subprocess.check_output(["powershell", "-Command", ps_command]).decode("utf-8").strip()
                if output:
                    pids = [p.strip() for p in output.split("\n") if p.strip()]
                    for pid in pids:
                        if pid:
                            subprocess.call(["taskkill", "/F", "/PID", pid, "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as ps_err:
                # If it's a CalledProcessError with return code 1, it just means no processes matched the query
                if not (isinstance(ps_err, subprocess.CalledProcessError) and ps_err.returncode == 1):
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
        else:
            # Unix (macOS / Linux) logic
            import signal
            
            # We NO LONGER use AppleScript to close Terminal windows by name
            # because it indiscriminately closes windows for ALL projects running 
            # with those titles, which shuts down other environments on the same machine.
            
            # 1. Kill process listening on the current server's port
            try:
                pid_bytes = subprocess.check_output(["lsof", "-ti", str(SERVER_PORT)])
                pids = pid_bytes.decode("utf-8").strip().split()
                for pid_str in pids:
                    pid = int(pid_str)
                    os.kill(pid, signal.SIGKILL)
                    safe_log_print(f"Killed process {pid} listening on port {SERVER_PORT}")
            except Exception:
                pass
            
            # 2. Safely kill ngrok and python processes spawned from THIS directory ONLY
            current_pid = os.getpid()
            project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__)))
            try:
                output = subprocess.check_output(["ps", "-eo", "pid,command"]).decode("utf-8")
                for line in output.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(None, 1)
                    if len(parts) < 2:
                        continue
                    pid_str, cmd = parts
                    try:
                        pid = int(pid_str)
                        if pid == current_pid:
                            continue
                        
                        cmd_lower = cmd.lower()
                        is_target = False
                        if "python" in cmd_lower and ("app.main" in cmd or "auto_update.py" in cmd or "force_restart.py" in cmd):
                            is_target = True
                        elif "ngrok" in cmd_lower:
                            is_target = True
                            
                        if is_target:
                            # Verify the process belongs to this project's directory
                            try:
                                lsof_out = subprocess.check_output(["lsof", "-p", str(pid), "-a", "-d", "cwd", "-Fn"]).decode("utf-8")
                                is_match = False
                                for lline in lsof_out.splitlines():
                                    if lline.startswith("n"):
                                        cwd = lline[1:]
                                        if os.path.abspath(cwd) == project_dir:
                                            is_match = True
                                            break
                                if is_match:
                                    os.kill(pid, signal.SIGKILL)
                                    safe_log_print(f"Killed old update/server/ngrok process: PID {pid} ({cmd}) in project dir")
                            except Exception:
                                pass
                    except (ValueError, OSError):
                        pass
            except Exception as e:
                safe_log_print(f"Error cleaning up Unix processes: {e}")
        
        safe_log_print("All old server/ngrok processes and terminal windows killed.")
    except Exception as e:
        safe_log_print(f"Error during cleanup of old processes: {e}")

    # 3. Wait for OS to fully release port 4444
    safe_log_print("Waiting for OS to release port 4444...")
    time.sleep(5)

    # 4. Start the new Server
    if is_windows:
        safe_log_print("Starting Server in NEW visible terminal...")
        try:
            start_bat = os.path.abspath(os.path.join("batch_scripts", "run_server.bat"))
            if os.path.exists(start_bat):
                # 0x00000010 is subprocess.CREATE_NEW_CONSOLE on Windows
                subprocess.Popen(f'"{start_bat}" --no-pause', shell=True, creationflags=0x00000010)
                safe_log_print("run_server.bat launched in new window.")
            else:
                safe_log_print(f"ERROR: Could not find {start_bat}")
        except Exception as e:
            safe_log_print(f"ERROR starting Server: {e}")
    else:
        # Start Server on macOS / Unix
        start_bat = os.path.abspath(os.path.join("batch_scripts", "run_server.bat"))
        launched_visually = False
        
        if sys.platform == 'darwin':
            safe_log_print("Starting Server in NEW macOS Terminal window...")
            try:
                project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__)))
                command_str = f"cd '{project_dir}' && bash '{start_bat}' --no-pause"
                applescript = f'tell application "Terminal" to do script "{command_str}"'
                subprocess.Popen(["osascript", "-e", applescript], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                launched_visually = True
                safe_log_print("run_server.bat launched in new macOS Terminal window.")
            except Exception as os_err:
                safe_log_print(f"macOS Terminal launch failed ({os_err}), falling back to background session.")
                
        if not launched_visually:
            safe_log_print("Starting Server in background session...")
            try:
                if os.path.exists(start_bat):
                    subprocess.Popen(["bash", start_bat], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    safe_log_print("run_server.bat launched successfully in background session.")
                else:
                    safe_log_print(f"ERROR: Could not find {start_bat}")
            except Exception as e:
                safe_log_print(f"ERROR starting Server: {e}")

    # 5. CRITICAL: Wait until the server is actually listening on port 4444
    #    before starting ngrok. This is what caused ERR_NGROK_8012 before —
    #    ngrok was starting while server was still running pip install / booting.
    wait_for_server(port=SERVER_PORT, timeout=SERVER_STARTUP_TIMEOUT)

    # 6. Start Ngrok ONLY AFTER the server is confirmed up
    if is_windows:
        safe_log_print("Starting Ngrok in NEW visible terminal...")
        try:
            ngrok_bat = os.path.abspath(os.path.join("batch_scripts", "run_ngrok.bat"))
            if os.path.exists(ngrok_bat):
                # 0x00000010 is subprocess.CREATE_NEW_CONSOLE on Windows
                subprocess.Popen(f'"{ngrok_bat}" --no-pause', shell=True, creationflags=0x00000010)
                safe_log_print("Ngrok restarted in new window.")
            else:
                safe_log_print(f"ERROR: Could not find {ngrok_bat}")
        except Exception as e:
            safe_log_print(f"ERROR restarting Ngrok: {e}")
    else:
        # Start Ngrok on macOS / Unix
        ngrok_bat = os.path.abspath(os.path.join("batch_scripts", "run_ngrok.bat"))
        launched_visually = False
        
        if sys.platform == 'darwin':
            safe_log_print("Starting Ngrok in NEW macOS Terminal window...")
            try:
                project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__)))
                command_str = f"cd '{project_dir}' && bash '{ngrok_bat}' --no-pause"
                applescript = f'tell application "Terminal" to do script "{command_str}"'
                subprocess.Popen(["osascript", "-e", applescript], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                launched_visually = True
                safe_log_print("Ngrok restarted in new macOS Terminal window.")
            except Exception as os_err:
                safe_log_print(f"macOS Ngrok Terminal launch failed ({os_err}), falling back to background session.")
                
        if not launched_visually:
            safe_log_print("Starting Ngrok in background session...")
            try:
                if os.path.exists(ngrok_bat):
                    subprocess.Popen(["bash", ngrok_bat], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    safe_log_print("Ngrok restarted successfully in background session.")
                else:
                    safe_log_print(f"ERROR: Could not find {ngrok_bat}")
            except Exception as e:
                safe_log_print(f"ERROR restarting Ngrok: {e}")
        
    safe_log_print("Force Restart Process Finished. Baton handed over to new instance.")
    safe_log_print("--------------------------------------------------")
    os._exit(0)

if __name__ == "__main__":
    execute_force_restart()
