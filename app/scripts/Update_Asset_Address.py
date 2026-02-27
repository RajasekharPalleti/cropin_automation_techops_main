
"""
Updates address details for assets based on configured keys.

Inputs:
Excel file with 'asset_id' and columns for address values (e.g., address_value_1).
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
        api_url = "https://cloud.cropin.in/services/asset/api/assets"
        log(f"Using default Asset API URL: {api_url}")

    # User Request: 
    # GET: {api_url}/{id}
    # PUT: {api_url} with multipart
    
    put_url_final = api_url
    get_url_base = api_url

    delay_time = float(config.get("delay_time", 1))  # seconds, configurable via UI

    # Attribute Keys (Dynamic) - These will be keys inside "address" dict
    attr_keys = config.get("attr_keys", [])
    valid_keys_map = {} # {index: key_name}
    for i, key in enumerate(attr_keys):
        if key and key.strip():
            valid_keys_map[i] = key.strip()

    if not valid_keys_map:
        log("⚠️ No Address Keys configured! Please enter at least one key (e.g. sublocalityLevel2) in the UI.")

    log(f"📘 Loading Excel file: {input_excel_file}")
    
    try:
        df = pd.read_excel(input_excel_file)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    # Check for asset_id
    id_col = 'asset_id'
    # Try finding case-insensitive or 'assetId' or 'id'
    possible = [c for c in df.columns if c.lower().replace('_','') in ['assetid', 'asset_id', 'id']]
    if possible:
            id_col = possible[0]
            log(f"ℹ️ Found ID column: {id_col}")
    else:
            # Fallback to col 0 if named appropriately or just assume 0
            id_col = df.columns[0]
            log(f"⚠️ 'asset_id' column not found. Using first column: {id_col}")

    # Ensure Status columns exist
    if "Status" not in df.columns:
        df["Status"] = ""
    if "Response" not in df.columns:
        df["Response"] = ""

    # Split for threading
    chunk_size = len(df) // 2 if len(df) > 0 else 1
    chunks = [df.iloc[i:i + chunk_size].copy() for i in range(0, len(df), chunk_size)]
    if not chunks: chunks = [df]

    # Determine column mapping
    key_col_map = {} # {key_name: column_name_in_df}
    
    available_cols = list(df.columns)
    
    for key_idx, key_name in valid_keys_map.items():
        # 1. Try explicit "address_value_X"
        preferred_col = f"address_value_{key_idx + 1}"
        
        if preferred_col in available_cols:
            key_col_map[key_name] = preferred_col
        # 2. Try explicit key name
        elif key_name in available_cols:
             key_col_map[key_name] = key_name
        # 3. Fallback: Use Column Index (Key 0 -> Col 1, Key 1 -> Col 2)
        else:
            target_col_idx = key_idx + 1
            if target_col_idx < len(available_cols):
                fallback_col = available_cols[target_col_idx]
                key_col_map[key_name] = fallback_col
                log(f"⚠️ Header not found for '{key_name}'. Using Column #{target_col_idx+1}: '{fallback_col}'")
            else:
                log(f"❌ Key '{key_name}' requires Column #{target_col_idx+1}, but file only has {len(available_cols)} columns.")
    
    # Validate we found columns for all keys
    missing = [k for k in valid_keys_map.values() if k not in key_col_map]
    if missing:
        log(f"❌ Could not map columns for keys: {missing}")
        return

    log(f"🔄 Starting processing {len(df)} assets. Column Mapping: {key_col_map}")
    
    # Thread Function
    def process_chunk(df_chunk, thread_id):
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        results = [] # List of (index, status, response)

        for index, row in df_chunk.iterrows():
            asset_id = str(row.get(id_col, "")).strip()
            
            status = ""
            response_str = ""
            
            if not asset_id or asset_id.lower() == 'nan':
                 results.append((index, "Skipped: Empty ID", ""))
                 continue

            try:
                # log(f"[Thread {thread_id}] Fetching: {asset_id}")
                get_resp = requests.get(f"{get_url_base}/{asset_id}", headers=headers)
                get_resp.raise_for_status()
                asset_data = get_resp.json()

                updates_made = False

                if "address" in asset_data and isinstance(asset_data["address"], dict):
                    # Dynamic Update using pre-calculated map
                    for key_name, col_name in key_col_map.items():
                        if col_name in df.columns:
                            new_value = row[col_name]
                            if pd.isna(new_value):
                                new_value = ""
                            else:
                                new_value = str(new_value).strip()
                            
                            current_val = asset_data["address"].get(key_name, "")
                            if str(current_val) != new_value:
                                asset_data["address"][key_name] = new_value
                                updates_made = True
                else:
                    status = "Failed: No address data"
                    results.append((index, status, ""))
                    continue

                if not updates_made:
                     # log(f"[Thread {thread_id}] No changes for {asset_id}")
                     results.append((index, "Skipped: No changes", ""))
                     continue
                
                # PUT
                
                # For multipart/form-data, do NOT manually set Content-Type.
                put_headers = {"Authorization": f"Bearer {token}"}

                multipart_data = {
                    "dto": (None, json.dumps(asset_data), "application/json")
                }
                
                put_resp = requests.put(put_url_final, headers=put_headers, files=multipart_data)
                put_resp.raise_for_status()

                status = "Success"
                response_str = put_resp.text[:600]
                log(f"[Thread {thread_id}] ✅ Success: {asset_id}")

            except Exception as e:
                # Capture full response text if available for better debugging
                error_details = ""
                if hasattr(e, 'response') and e.response is not None:
                     error_details = f" - Server Response: {e.response.text[:200]}"
                
                status = f"Failed: {str(e)}"
                response_str = str(e) + error_details
                log(f"[Thread {thread_id}] ❌ Failed: {asset_id} - {e}{error_details}")

            time.sleep(delay_time)
            results.append((index, status, response_str))

        return results

    # Execute Threads
    max_workers = 2
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i, chunk in enumerate(chunks):
             futures.append(executor.submit(process_chunk, chunk, i+1))
        
        chunk_results = []
        for f in futures:
            chunk_results.extend(f.result())

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
