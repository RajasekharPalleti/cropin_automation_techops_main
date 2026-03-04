"""
Updates asset details (e.g., name, soilType, irrigationType,deleted etc) based on configured keys.

Inputs:
Excel file with 'asset_id'.
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
        api_url = "https://cloud.cropin.in/services/farm/api/assets"
        log(f"Using default Asset API URL: {api_url}")
    api_url = api_url.rstrip('/')

    delay_time = float(config.get("delay_time", 0.2))  # seconds, configurable via UI

    # Attribute Keys (Dynamic)
    attr_keys = config.get("attr_keys", [])
    valid_keys_map = {} # {index: key_name}
    for i, key in enumerate(attr_keys):
        if key and key.strip():
            valid_keys_map[i] = key.strip()

    if not valid_keys_map:
        log("⚠️ No Keys configured! Please enter at least one field key (e.g., name) in the UI.")

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
        # Try finding case-insensitive or 'assetID'
        possible = [c for c in df.columns if c.lower().replace('_','') in ['assetid', 'asset_id', 'id']]
        if possible:
             id_col = possible[0]
             log(f"ℹ️ Found ID column: {id_col}")
        else:
             # Fallback to col 0
             id_col = df.columns[0]
             log(f"⚠️ 'asset_id' column not found. Using first column: {id_col}")

    # Ensure Status columns exist
    if "Status" not in df.columns:
        df["Status"] = ""
    if "Response" not in df.columns:
        df["Response"] = ""

    # Split for threading
    mid_index = len(df) // 2
    chunk1 = df.iloc[:mid_index].copy()
    chunk2 = df.iloc[mid_index:].copy()

    log(f"🔄 Starting processing {len(df)} assets with 2 threads. Updating Keys: {list(valid_keys_map.values())}")
    
    # Thread Function
    def process_chunk(df_chunk, thread_id):
        headers = {"Authorization": f"Bearer {token}"}
        results = [] # List of (index, status, response)

        for index, row in df_chunk.iterrows():
            asset_id = str(row.get(id_col, "")).strip()
            
            status = ""
            response_str = ""
            
            if not asset_id or asset_id.lower() == 'nan':
                 log(f"[Thread {thread_id}] Skipping empty row {index}")
                 results.append((index, "Skipped: Empty ID", ""))
                 continue

            try:
                log(f"[Thread {thread_id}] Fetching: {asset_id}")
                get_resp = requests.get(f"{api_url}/{asset_id}", headers=headers)
                get_resp.raise_for_status()
                asset_data = get_resp.json()

                updates_made = False

                # Dynamic Update Logic
                for key_idx, key_name in valid_keys_map.items():
                    col_name = f"value_{key_idx + 1}"
                    
                    if col_name in df.columns:
                        raw_value = row[col_name]
                        if pd.isna(raw_value):
                            raw_value = ""

                        final_value = str(raw_value).strip()
                        is_complex = False

                        # Try parsing as JSON if string looks like object/list
                        if isinstance(raw_value, str):
                            s_val = raw_value.strip()
                            if (s_val.startswith('{') and s_val.endswith('}')) or \
                               (s_val.startswith('[') and s_val.endswith(']')):
                                try:
                                    parsed_json = json.loads(s_val)
                                    final_value = parsed_json
                                    is_complex = True
                                except Exception:
                                    pass

                        # Compare with existing
                        current_value = asset_data.get(key_name)
                        
                        update_needed = False
                        if is_complex:
                             if current_value != final_value:
                                 update_needed = True
                        else:
                             curr_str = str(current_value).strip() if current_value is not None else ""
                             if curr_str != final_value:
                                 update_needed = True
                        
                        if update_needed:
                            asset_data[key_name] = final_value
                            updates_made = True
                    else:
                        pass

                if not updates_made:
                     log(f"[Thread {thread_id}] No changes for {asset_id}")
                     results.append((index, "Skipped: No changes", ""))
                     continue
                
                # PUT - Use Multipart/DTO (Assuming Asset API works same as Farmer API)
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
