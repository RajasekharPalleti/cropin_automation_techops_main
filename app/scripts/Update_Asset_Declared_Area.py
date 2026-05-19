"""
Updates the declared area of an asset.

Inputs:
Excel file with 'asset_id' and 'declaredArea' (which represents the count of the declared area).
"""
import pandas as pd
import requests
import json
import time
from concurrent.futures import ThreadPoolExecutor
import threading

# Author: Rajasekhar Palleti

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    # 1. Config & Validation
    token = config.get("token")
    if not token:
        log("❌ No token provided in configuration.")
        return

    # API URL
    api_url = config.get("base_api_url")
    if not api_url:
        api_url = "https://cloud.cropin.in/services/farm/api/assets"
        log(f"Using default Asset API URL: {api_url}")
    api_url = api_url.rstrip('/')

    delay_time = float(config.get("delay_time", 0.2))  # seconds, configurable via UI

    log(f"📘 Loading Excel file: {input_excel_file}")
    
    try:
        df = pd.read_excel(input_excel_file)
        # remove unnamed columns
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    # Check for asset_id
    id_col = 'asset_id'
    if id_col not in df.columns:
        possible = [c for c in df.columns if c.lower().replace('_','') in ['assetid', 'asset_id', 'id']]
        if possible:
             id_col = possible[0]
             log(f"ℹ️ Found ID column: {id_col}")
        else:
             id_col = df.columns[0]
             log(f"⚠️ 'asset_id' column not found. Using first column: {id_col}")

    # Ensure required columns
    if "declaredArea" not in df.columns:
        log("❌ 'declaredArea' column not found in the Excel file.")
        return

    # Ensure Status columns exist and are explicitly cast to string to prevent TypeError
    if "Status" not in df.columns:
        df["Status"] = ""
    df["Status"] = df["Status"].fillna("").astype(str)
    
    if "Response" not in df.columns:
        df["Response"] = ""
    df["Response"] = df["Response"].fillna("").astype(str)

    # Split for threading
    mid_index = len(df) // 2
    chunk1 = df.iloc[:mid_index].copy()
    chunk2 = df.iloc[mid_index:].copy()

    total_rows = len(df)
    processed_count = 0
    processed_lock = threading.Lock()
    log(f"🔄 Starting processing {total_rows} assets with 2 threads.")
    
    def process_chunk(df_chunk, thread_id):
        nonlocal processed_count
        headers = {"Authorization": f"Bearer {token}"}
        results = [] 

        for index, row in df_chunk.iterrows():
            asset_id = str(row.get(id_col, "")).strip()
            declared_area_val = row.get("declaredArea")
            
            status = ""
            response_str = ""
            
            try:
                if not asset_id or asset_id.lower() == 'nan':
                    log(f"[Thread {thread_id}] Skipping empty row {index}")
                    results.append((index, "Skipped: Empty ID", ""))
                    continue

                if pd.isna(declared_area_val) or str(declared_area_val).strip() == '':
                    log(f"[Thread {thread_id}] Skipping {asset_id}: declaredArea is empty")
                    results.append((index, "Skipped: Empty declaredArea", ""))
                    continue

                try:
                    declared_area_count = float(declared_area_val)
                except ValueError:
                    log(f"[Thread {thread_id}] Skipping {asset_id}: invalid declaredArea value {declared_area_val}")
                    results.append((index, "Skipped: Invalid declaredArea", ""))
                    continue

                try:
                    log(f"[Thread {thread_id}] Fetching: {asset_id}")
                    get_resp = requests.get(f"{api_url}/{asset_id}", headers=headers)
                    get_resp.raise_for_status()
                    asset_data = get_resp.json()

                    current_declared = asset_data.get("declaredArea")
                    current_count = current_declared.get("count") if current_declared else None

                    if current_count == declared_area_count:
                        log(f"[Thread {thread_id}] No changes for {asset_id}")
                        results.append((index, "Skipped: No changes", ""))
                        continue
                    
                    # Update the declaredArea
                    if not asset_data.get("declaredArea"):
                        asset_data["declaredArea"] = {}
                    asset_data["declaredArea"]["count"] = declared_area_count

                    time.sleep(delay_time)
                    
                    multipart_data = {
                        "dto": (None, json.dumps(asset_data), "application/json")
                    }
                    
                    put_resp = requests.put(api_url, headers=headers, files=multipart_data)
                    put_resp.raise_for_status()

                    status = "Success"
                    response_str = put_resp.text[:600]
                    log(f"[Thread {thread_id}] ✅ Success: {asset_id}")

                except Exception as e:
                    status = f"Failed: {str(e)}"
                    response_str = str(e)
                    log(f"[Thread {thread_id}] ❌ Failed: {asset_id} - {e}")

                time.sleep(delay_time)
                results.append((index, status, response_str))
            finally:
                with processed_lock:
                    processed_count += 1
                    pending_rows = total_rows - processed_count
                    log(f"[Thread {thread_id}] Processed: {processed_count}/{total_rows} | Pending: {pending_rows} | Asset: {asset_id if asset_id and asset_id.lower() != 'nan' else 'N/A'}")

        return results

    # Execute Threads
    with ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(process_chunk, chunk1, 1)
        future2 = executor.submit(process_chunk, chunk2, 2)
        
        chunk_results = []
        chunk_results.extend(future1.result())
        chunk_results.extend(future2.result())

    # Update Main DataFrame
    log("💾 Aggregating results...")
    for idx, status, response in chunk_results:
        if idx in df.index:
            df.at[idx, "Status"] = status
            df.at[idx, "Response"] = str(response)

    # Save
    try:
        df.to_excel(output_excel_file, index=False)
        log(f"📁 Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"Error saving file: {e}")
