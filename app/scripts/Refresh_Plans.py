"""
Triggers a refresh of crop plans by fetching and re-submitting data.

Inputs:
Excel file with 'ca_id' column.
"""
# ca_id is read from an Excel file. Each ca_id is processed using GET and PUT APIs with retries.
# The results are saved back to a new Excel file.

import pandas as pd
import requests
import json
import time
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_RETRIES = 1  # Number of retries for GET/PUT
TIME_OUT = 5  # seconds

WAIT_TIME = 2  # seconds between PUT calls
MAX_WORKERS = 4  # number of threads
# =================================================

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    token = config.get("token")
    if not token:
        log("❌ No token provided in configuration.")
        return

    # Derive URLs from config
    # Default Base: https://cloud.cropin.in/services/farm/api/croppable-areas/
    base_url = config.get("base_api_url", "").strip().rstrip('/')
    if not base_url:
        base_url = "https://cloud.cropin.in/services/farm/api/croppable-areas"
        log(f"⚠️ No Base URL provided, defaulting to: {base_url}")

    delay_time = float(config.get("delay_time", 2))  # configurable via UI
    
    # GET URL:  Base + /<id> -> https://cloud.cropin.in/services/farm/api/croppable-areas/<id>
    # Ensure base_url ends correctly for appending ID later
    
    # PUT URL: .../croppablearea/tasks...
    # Logic: if base ends with 'croppable-areas', replace with 'croppablearea' for PUT
    
    get_url_template = f"{base_url}/"
    
    if "croppable-areas" in base_url:
        put_url = base_url.replace("croppable-areas", "croppablearea") + "/tasks?sort=lastModifiedDate,desc"
    else:
        # Fallback exact URL if user provided something else or base structure differs
        put_url = "https://cloud.cropin.in/services/farm/api/croppablearea/tasks?sort=lastModifiedDate,desc"
        log(f"⚠️ Base URL pattern mismatch. Using default PUT URL: {put_url}")

    log(f"🔗 Configuration:\n   GET Base: {get_url_template}<ID>\n   PUT URL:  {put_url}")

    def request_with_retry(method, url, headers=None, data=None, timeout=TIME_OUT, retries=MAX_RETRIES):
        """
        Generic request with retry mechanism.
        """
        for attempt in range(1, retries + 1):
            try:
                if method.upper() == "GET":
                    resp = requests.get(url, headers=headers, timeout=timeout)
                elif method.upper() == "PUT":
                    resp = requests.put(url, headers=headers, data=data, timeout=timeout)
                else:
                    raise ValueError("Unsupported HTTP method")

                if resp.status_code in [200, 201]:
                    return resp
                else:
                    log(f"⚠️ Attempt {attempt} failed for URL: {url} | Status Code: {resp.status_code}")
            except Exception as e:
                log(f"⚠️ Attempt {attempt} exception for URL: {url} | {e}")
            time.sleep(delay_time)  # wait before retry
        return None


    def process_croppable_area(ca_id, token, row_number=None):
        """
        Fetch croppable area data using GET API and send it to the PUT API.
        Accepts an optional row_number to indicate which Excel row is being processed.
        Returns a dict with CA_id, row_number, status, response, and timestamps.
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_ts = time.time()

        # Print the Excel row number (1-based) if provided
        log(f"🟢 Started processing CA_id: {ca_id} at {start_time} | Row: {row_number}")

        try:
            # Step 1️⃣: GET croppable area data with retries
            get_url = f"{get_url_template}{ca_id}"
            get_resp = request_with_retry("GET", get_url, headers=headers)

            if not get_resp:
                end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                duration = round(time.time() - start_ts, 2)
                log(f"🔴 Completed CA_id: {ca_id} | Status: Failed | Duration: {duration}s")
                return {
                    "ca_id": ca_id,
                    "row_number": row_number,
                    "status": "Failed",
                    "response": f"GET failed after {MAX_RETRIES} attempts",
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration_seconds": duration
                }

            ca_data = get_resp.json()

            # Step 2️⃣: Wait before PUT call
            time.sleep(delay_time)

            log(f"🟡 Sending PUT request for CA_id: {ca_id}...")

            # Step 3️⃣: PUT API call with retries
            # put_url is from outer scope (run function)
            put_resp = request_with_retry("PUT", put_url, headers=headers, data=json.dumps(ca_data))

            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            duration = round((time.time()-delay_time) - start_ts, 2)

            if put_resp:
                log(f"✅ Completed CA_id: {ca_id} | Status: Success | Duration: {duration}s")
                return {
                    "ca_id": ca_id,
                    "row_number": row_number,
                    "status": "Success",
                    "response": put_resp.text,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration_seconds": duration
                }
            else:
                log(f"🔴 Completed CA_id: {ca_id} | Status: Failed | Duration: {duration}s")
                return {
                    "ca_id": ca_id,
                    "row_number": row_number,
                    "status": "Failed",
                    "response": f"PUT failed after {MAX_RETRIES} attempts",
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration_seconds": duration
                }

        except Exception as e:
            traceback.print_exc()
            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            duration = round((time.time()-delay_time) - start_ts, 2)
            log(f"⚠️ Error processing CA_id: {ca_id} | Duration: {duration}s")
            return {
                "ca_id": ca_id,
                "row_number": row_number,
                "status": "Failed",
                "response": str(e),
                "start_time": start_time,
                "end_time": end_time,
                "duration_seconds": duration
            }


    log("📘 Loading Excel file...")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"Error reading Excel file: {e}")
        return

    if "ca_id" not in df.columns:
        log("❌ 'ca_id' column not found in Excel sheet!")
        return

    total_rows = len(df)
    processed_count = 0
    import threading
    processed_lock = threading.Lock()
    log(f"🔄 Starting with {total_rows} croppable areas using {MAX_WORKERS} workers...")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Pass the Excel row number (1-based) to the worker so it can print it.
        futures = {
            executor.submit(process_croppable_area, ca_id, token, idx): ca_id
            for idx, ca_id in enumerate(df["ca_id"], start=1)
        }

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            with processed_lock:
                processed_count += 1
                pending_rows = total_rows - processed_count
                log(f"Progress: {processed_count}/{total_rows} | Pending: {pending_rows}")

    # Merge results and save
    log("Processing complete. Merging results...")
    results_df = pd.DataFrame(results)
    # We merge on ca_id. Note: if ca_id is duplicated in input, this simple merge might duplicate rows. 
    # But for now we stick to user logic.
    # Actually, simpler is to just return results_df or merge carefully.
    # The user logic was: df = df.merge(results_df, how="left", on="ca_id")
    df = df.merge(results_df, how="left", on="ca_id")
    
    # Ensure status/response columns are explicitly cast to string to avoid TypeError
    for col in ["status", "response"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    try:
        df.to_excel(output_excel_file, index=False)
        log(f"📁 Execution complete. Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"Error saving output file: {e}")
