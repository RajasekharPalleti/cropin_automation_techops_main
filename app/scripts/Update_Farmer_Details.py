"""
Updates farmer details (e.g., firstName, farmerCode, email etc..) based on configured keys.

Inputs:
Excel file with 'farmer_id'.
Columns for updates should be named 'value_1', 'value_2', etc., corresponding
to the order of keys configured in the UI.
"""
import pandas as pd
import requests
import json
import time

from concurrent.futures import ThreadPoolExecutor

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
        api_url = "https://cloud.cropin.in/services/farm/api/farmers"
        log(f"Using default Farmer API URL: {api_url}")
    api_url = api_url.rstrip('/')

    delay_time = float(config.get("delay_time", 0.2))  # seconds, configurable via UI

    # Attribute Keys (Dynamic)
    # Reusing 'attr_keys' from config which is populated by the generic attribute UI
    attr_keys = config.get("attr_keys", [])
    valid_keys_map = {} # {index: key_name}
    for i, key in enumerate(attr_keys):
        if key and key.strip():
            valid_keys_map[i] = key.strip()

    if not valid_keys_map:
        log("⚠️ No Keys configured! Please enter at least one field key (e.g., firstName) in the UI.")

    log(f"📘 Loading Excel file: {input_excel_file}")
    
    try:
        df = pd.read_excel(input_excel_file)
        # remove unnamed columns
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    # Check for farmer_id
    id_col = 'farmer_id'
    if id_col not in df.columns:
        # Try finding case-insensitive or 'farmerID'
        possible = [c for c in df.columns if c.lower().replace('_','') in ['farmerid', 'farmer_id', 'id']]
        if possible:
             id_col = possible[0]
             log(f"ℹ️ Found ID column: {id_col}")
        else:
             # Fallback to col 0
             id_col = df.columns[0]
             log(f"⚠️ 'farmer_id' column not found. Using first column: {id_col}")

    # Ensure Status columns exist and are explicitly cast to string to avoid TypeError
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
    import threading
    processed_lock = threading.Lock()
    log(f"🔄 Starting processing {total_rows} farmers with 2 threads. Updating Keys: {list(valid_keys_map.values())}")
    
    # Thread Function
    def process_chunk(df_chunk, thread_id):
        nonlocal processed_count
        headers = {"Authorization": f"Bearer {token}"}
        results = [] # List of (index, status, response)

        for index, row in df_chunk.iterrows():
            farmer_id = str(row.get(id_col, "")).strip()
            
            status = ""
            response_str = ""
            
            try:
                if not farmer_id or farmer_id.lower() == 'nan':
                    log(f"[Thread {thread_id}] Skipping empty row {index}")
                    results.append((index, "Skipped: Empty ID", ""))
                    continue

                try:
                    log(f"[Thread {thread_id}] Fetching: {farmer_id}")
                    get_resp = requests.get(f"{api_url}/{farmer_id}", headers=headers)
                    get_resp.raise_for_status()
                    farmer_data = get_resp.json()

                    updates_made = False

                    # Dynamic Update Logic
                    for key_idx, key_name in valid_keys_map.items():
                        # Map config key index 0 -> value_1, index 1 -> value_2...
                        col_name = f"value_{key_idx + 1}"
                        
                        if col_name in df.columns:
                            new_value = row[col_name]
                            if pd.isna(new_value):
                                new_value = "" # or None? Empty string for text fields usually safe.
                            else:
                                new_value = str(new_value).strip()
                            
                            # Compare with existing
                            current_value = farmer_data.get(key_name)
                            if current_value is None: current_value = ""
                            
                            if str(current_value).strip() != new_value:
                                farmer_data[key_name] = new_value
                                updates_made = True
                        else:
                            # Column not found for this key
                            pass

                    if not updates_made:
                        log(f"[Thread {thread_id}] No changes for {farmer_id}")
                        results.append((index, "Skipped: No changes", ""))
                        continue
                    
                    # PUT - Use Multipart/DTO as requested
                    time.sleep(delay_time)
                    
                    multipart_data = {
                        "dto": (None, json.dumps(farmer_data), "application/json")
                    }
                    
                    put_resp = requests.put(api_url, headers=headers, files=multipart_data)
                    
                    put_resp.raise_for_status()

                    status = "Success"
                    response_str = put_resp.text[:300]
                    log(f"[Thread {thread_id}] ✅ Success: {farmer_id}")

                except Exception as e:
                    status = f"Failed: {str(e)}"
                    response_str = str(e)
                    log(f"[Thread {thread_id}] ❌ Failed: {farmer_id} - {e}")

                time.sleep(delay_time)
                results.append((index, status, response_str))
            finally:
                with processed_lock:
                    processed_count += 1
                    pending_rows = total_rows - processed_count
                    log(f"[Thread {thread_id}] Processed: {processed_count}/{total_rows} | Pending: {pending_rows} | Farmer: {farmer_id if farmer_id and farmer_id.lower() != 'nan' else 'N/A'}")

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
