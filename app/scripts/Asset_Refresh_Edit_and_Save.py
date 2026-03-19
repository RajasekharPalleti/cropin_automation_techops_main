"""
Refreshes Assets using GET + PUT with Multithreading.

Inputs:
Excel file with 'asset_id' column.
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

    api_url = config.get("base_api_url")
    if not api_url:
        api_url = "https://cloud.cropin.in/services/farm/api/assets"
        log(f"Using default Asset API URL: {api_url}")
    
    api_url = api_url.rstrip('/')

    MAX_RETRIES = 2
    MAX_WORKERS = 4
    delay_time = float(config.get("delay_time", 1))
    # ========================================== #

    headers = {
        "Authorization": f"Bearer {token}"
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

    # Explicitly cast to string after filling NaNs to prevent TypeError in newer pandas versions
    df["Status"] = df["Status"].fillna("").astype(str)
    df["Message"] = df["Message"].fillna("").astype(str)

    # Ensure asset_id exists
    id_col = None
    possible_cols = ['asset_id', 'assetId', 'id', 'Id', 'ID']
    for col in df.columns:
        if col in possible_cols:
            id_col = col
            break
    
    if not id_col:
        id_col = df.columns[0]
        log(f"⚠️ 'asset_id' column not explicitly found. Using first column: {id_col}")

    # -------------------------------------------------
    # Worker function
    # -------------------------------------------------
    def process_asset(index, asset_id):
        if pd.isna(asset_id):
            return index, "SKIPPED", "Asset ID missing"

        try:
             asset_id = int(float(asset_id))
        except:
             return index, "SKIPPED", f"Invalid ID format: {asset_id}"

        log(f"🔄 Processing Asset ID: {asset_id}")

        last_error = "Unknown error"

        for _ in range(MAX_RETRIES):
            try:
                # -------- GET --------
                get_resp = requests.get(f"{api_url}/{asset_id}", headers=headers)

                if get_resp.status_code != 200:
                    last_error = f"GET Failed: {get_resp.status_code}"
                    time.sleep(delay_time)
                    continue

                asset_data = get_resp.json()

                # Skip deleted assets
                if asset_data.get("deleted") is True:
                    return index, "SKIPPED", "Asset is deleted"

                # -------- PUT (NO ID IN URL) --------
                multipart_data = {
                    "dto": (None, json.dumps(asset_data), "application/json")
                }

                put_resp = requests.put(
                    api_url,
                    headers=headers,
                    files=multipart_data
                )

                if put_resp.status_code in (200, 204):
                    log(f"✅ Refreshed: {asset_id}")
                    return index, "PASS", "Refreshed successfully"

                last_error = f"PUT Failed: {put_resp.status_code}"
                log(f"❌ PUT Failed {asset_id}: {put_resp.status_code}")
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
    processed_count = 0
    import threading
    processed_lock = threading.Lock()
    log(f"🚀 Starting processing {total_rows} assets with {MAX_WORKERS} threads...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for index, row in df.iterrows():
            futures.append(
                executor.submit(process_asset, index, row[id_col])
            )
            time.sleep(delay_time / 5.0) # Proportional delay to prevent burst

        completed_count = 0
        for future in as_completed(futures):
            index, status, message = future.result()
            df.at[index, "Status"] = status
            df.at[index, "Message"] = message
            with processed_lock:
                processed_count += 1
                pending_rows = total_rows - processed_count
                if processed_count % 5 == 0 or processed_count == total_rows:
                    log(f"Progress: {processed_count}/{total_rows} | Pending: {pending_rows}")

    log("💾 Writing output Excel...")
    try:
        df.to_excel(output_excel, index=False)
        log(f"✅ Done. Output saved.")
    except Exception as e:
        log(f"❌ Error saving output: {e}")
