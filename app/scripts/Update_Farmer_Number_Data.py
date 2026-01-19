"""
Updates farmer details inside the 'data' object (e.g., countryIsoCode, countryCode, mobileNumber) based on configured keys.

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
    api_url = config.get("post_api_url")
    if not api_url:
        api_url = "https://cloud.cropin.in/services/farm/api/farmers"
        log(f"Using default Farmer API URL: {api_url}")
    api_url = api_url.rstrip('/')

    # Attribute Keys (Dynamic)
    attr_keys = config.get("attr_keys", [])
    valid_keys_map = {} # {index: key_name}
    for i, key in enumerate(attr_keys):
        if key and key.strip():
            valid_keys_map[i] = key.strip()

    if not valid_keys_map:
        log("⚠️ No Keys configured! Please enter at least one field key (e.g., mobileNumber) in the UI.")

    log(f"📘 Loading Excel file: {input_excel_file}")
    
    try:
        df = pd.read_excel(input_excel_file)
        # remove unnamed columns
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        df.columns = df.columns.str.strip()
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    # Check for farmer_id
    id_col = 'farmer_id'
    possible_ids = [c for c in df.columns if c.lower().replace('_','') in ['farmerid', 'farmer_id', 'id', 'externalid']]
    if possible_ids:
        id_col = possible_ids[0]
        log(f"ℹ️ Found ID column: {id_col}")
    else:
        id_col = df.columns[0]
        log(f"⚠️ 'farmer_id' column not found. Using first column: {id_col}")

    # Ensure Status columns exist
    if "Status" not in df.columns:
        df["Status"] = ""
    if "Response" not in df.columns:
        df["Response"] = ""

    # Split for threading
    mid_index = len(df) // 2
    chunk1 = df.iloc[:mid_index].copy()
    chunk2 = df.iloc[mid_index:].copy()

    log(f"🔄 Starting processing {len(df)} farmers with 2 threads. Updating Keys in 'data': {list(valid_keys_map.values())}")
    
    # Thread Function
    def process_chunk(df_chunk, thread_id):
        headers = {"Authorization": f"Bearer {token}"}
        results = [] # List of (index, status, response)

        for index, row in df_chunk.iterrows():
            farmer_id = str(row.get(id_col, "")).strip()
            
            status = ""
            response_str = ""
            
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

                # Ensure 'data' object exists
                if 'data' not in farmer_data or farmer_data['data'] is None:
                    farmer_data['data'] = {}

                # Dynamic Update Logic
                for key_idx, key_name in valid_keys_map.items():
                    col_name = f"value_{key_idx + 1}"
                    
                    if col_name in df.columns:
                        new_value = row[col_name]
                        if pd.isna(new_value):
                            continue # Skip if empty in excel
                        
                        new_value_str = str(new_value).strip()
                        
                        # Compare with existing in 'data'
                        current_value = farmer_data['data'].get(key_name)
                        if current_value is None: current_value = ""
                        
                        if str(current_value).strip() != new_value_str:
                            farmer_data['data'][key_name] = new_value_str
                            updates_made = True
                    else:
                        # Optional: warn specific column missing?
                        pass

                if not updates_made:
                     log(f"[Thread {thread_id}] No changes for {farmer_id}")
                     results.append((index, "Skipped: No changes", ""))
                     continue
                
                # PUT
                time.sleep(0.2)
                
                multipart_data = {
                    "dto": (None, json.dumps(farmer_data), "application/json")
                }
                
                put_resp = requests.put(api_url, headers=headers, files=multipart_data)
                
                try:
                    put_resp.raise_for_status()
                    status = "Success"
                    response_str = put_resp.text[:300]
                    log(f"[Thread {thread_id}] ✅ Success: {farmer_id}")
                except requests.exceptions.HTTPError as err:
                     status = f"Failed: {put_resp.status_code}"
                     response_str = put_resp.text
                     log(f"[Thread {thread_id}] ❌ Failed: {farmer_id} - {response_str}")

            except Exception as e:
                status = f"Failed: {str(e)}"
                response_str = str(e)
                log(f"[Thread {thread_id}] ❌ Exception: {farmer_id} - {e}")

            time.sleep(0.2)
            results.append((index, status, response_str))

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
