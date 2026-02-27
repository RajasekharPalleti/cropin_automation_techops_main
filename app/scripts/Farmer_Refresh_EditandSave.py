"""
Refreshes Farmers using GET + PUT with Multithreading.

Inputs:
Excel file with 'farmer_id' column.
"""
import pandas as pd
import requests
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def run(input_excel, output_excel, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    # ================= CONFIG ================= #
    token = config.get("token")
    if not token:
        log("❌ No token provided.")
        return

    api_url = config.get("url")
    if not api_url:
        api_url = "https://cloud.cropin.in/services/farm/api/farmers"
        log(f"Using default Farmer API URL: {api_url}")
    
    api_url = api_url.rstrip('/')

    MAX_RETRIES = 2
    MAX_WORKERS = 4
    delay_time = float(config.get("delay_time", 1))
    # ========================================== #

    headers = {
        "Authorization": f"Bearer {token}"
        # ❌ Do NOT set Content-Type for multipart
    }

    log(f"📂 Reading Excel: {input_excel}")
    try:
        df = pd.read_excel(input_excel)
    except Exception as e:
        log(f"❌ Error reading Excel: {e}")
        return

    # Check columns
    if "Status" not in df.columns:
        df["Status"] = ""
    if "Message" not in df.columns:
        df["Message"] = ""

    # Ensure farmer_id exists
    # Allow 'farmer_id', 'farmerId', 'id', or column 0
    id_col = None
    possible_cols = ['farmer_id', 'farmerId', 'id', 'Id', 'ID']
    for col in df.columns:
        if col in possible_cols:
            id_col = col
            break
    
    if not id_col:
        id_col = df.columns[0]
        log(f"⚠️ 'farmer_id' column not explicitly found. Using first column: {id_col}")

    # -------------------------------------------------
    # Worker function
    # -------------------------------------------------
    def process_farmer(index, farmer_id):
        if pd.isna(farmer_id):
            return index, "SKIPPED", "Farmer ID missing"

        try:
            farmer_id = int(float(farmer_id)) # Handle floats
        except:
             return index, "SKIPPED", f"Invalid ID format: {farmer_id}"

        log(f"🔄 Processing Farmer ID: {farmer_id}")

        last_error = "Unknown error"

        for _ in range(MAX_RETRIES):
            try:
                # -------- GET --------
                get_resp = requests.get(f"{api_url}/{farmer_id}", headers=headers)

                if get_resp.status_code != 200:
                    last_error = f"GET Failed: {get_resp.status_code}"
                    # Don't log every retry failure to keep logs clean, unless critical
                    time.sleep(delay_time)
                    continue

                farmer_data = get_resp.json()

                # ✅ Skip deleted farmers
                if farmer_data.get("deleted") is True:
                    return index, "SKIPPED", "Farmer is deleted"

                # -------- PUT (NO ID IN URL) --------
                multipart_data = {
                    "dto": (None, json.dumps(farmer_data), "application/json")
                }

                put_resp = requests.put(
                    api_url,          # ✅ base URL only
                    headers=headers,
                    files=multipart_data
                )

                if put_resp.status_code in (200, 204):
                    log(f"✅ Refreshed: {farmer_id}")
                    return index, "PASS", "Refreshed successfully"

                last_error = f"PUT Failed: {put_resp.status_code}"
                log(f"❌ PUT Failed {farmer_id}: {put_resp.status_code}")
                time.sleep(delay_time)

            except Exception as e:
                last_error = str(e)
                time.sleep(delay_time)

        return index, "FAIL", last_error

    # -------------------------------------------------
    # Multithreading execution
    # -------------------------------------------------
    futures = []
    
    total_rows = len(df)
    log(f"🚀 Starting processing {total_rows} farmers with {MAX_WORKERS} threads...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for index, row in df.iterrows():
            futures.append(
                executor.submit(process_farmer, index, row[id_col])
            )
            time.sleep(0.1) # Small delay to prevent burst

        completed_count = 0
        for future in as_completed(futures):
            index, status, message = future.result()
            df.at[index, "Status"] = status
            df.at[index, "Message"] = message
            completed_count += 1
            if completed_count % 10 == 0:
                 log(f"Progress: {completed_count}/{total_rows}")

    log("💾 Writing output Excel...")
    try:
        df.to_excel(output_excel, index=False)
        log(f"✅ Done. Output saved.")
    except Exception as e:
        log(f"❌ Error saving output: {e}")
