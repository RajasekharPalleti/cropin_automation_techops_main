
"""
Updates address details for farmers based on configured keys.

Inputs:
Excel file with 'farmer_id' and columns for address values (e.g., address_value_1).
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

    # User Request: 
    # GET: {api_url}/{id}
    # PUT: {api_url} with multipart
    
    put_url_final = api_url
    get_url_base = api_url
    
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

    # Check for farmer_id
    id_col = 'farmer_id'
    # Try finding case-insensitive or 'farmerID'
    possible = [c for c in df.columns if c.lower().replace('_','') in ['farmerid', 'farmer_id', 'id']]
    if possible:
            id_col = possible[0]
            log(f"ℹ️ Found ID column: {id_col}")
    else:
            # Fallback to col 0 if named appropriately or just assume 0
            id_col = df.columns[0]
            log(f"⚠️ 'farmer_id' column not found. Using first column: {id_col}")

    # Ensure Status columns exist
    if "Status" not in df.columns:
        df["Status"] = ""
    if "Response" not in df.columns:
        df["Response"] = ""

    # Split for threading
    chunk_size = len(df) // 2 if len(df) > 0 else 1
    chunks = [df.iloc[i:i + chunk_size].copy() for i in range(0, len(df), chunk_size)]
    if not chunks: chunks = [df]

    log(f"🔄 Starting processing {len(df)} farmers. Updating Address Keys: {list(valid_keys_map.values())}")
    
    # Thread Function
    def process_chunk(df_chunk, thread_id):
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        results = [] # List of (index, status, response)

        for index, row in df_chunk.iterrows():
            farmer_id = str(row.get(id_col, "")).strip()
            
            status = ""
            response_str = ""
            
            if not farmer_id or farmer_id.lower() == 'nan':
                 results.append((index, "Skipped: Empty ID", ""))
                 continue

            try:
                log(f"🔄 Processing row {index+1}/{len(df)}: Fetching {farmer_id}")
                get_resp = requests.get(f"{get_url_base}/{farmer_id}", headers=headers)
                get_resp.raise_for_status()
                farmer_data = get_resp.json()

                updates_made = False

                if "address" in farmer_data and isinstance(farmer_data["address"], dict):
                    # Dynamic Update
                    for key_idx, key_name in valid_keys_map.items():
                        # We expect Excel headers to be "address_value_1", "address_value_2" or similar?
                        # Or user said "follow existing attribute code structure".
                        # In attribute code: "additional_attribute_{key_idx + 1}"
                        # Let's use "address_value_{key_idx + 1}" or just rely on column order?
                        # User example used "Village Name" in column 4.
                        # The "Update_Farmer_Addtl_Atrribute.py" maps user inputs (Dropdown) to Excel Columns "additional_attribute_1", etc.
                        # Let's stick to that pattern: "address_value_{i+1}"
                        
                        col_name = f"address_value_{key_idx + 1}"
                        
                        if col_name in df.columns:
                            new_value = row[col_name]
                            if pd.isna(new_value):
                                new_value = ""
                            else:
                                new_value = str(new_value).strip()
                            
                            # Update Address Dict
                            # Handle nested if key has dots? (e.g. "address.pincode") - No, user said valid_keys_map are keys inside address
                            
                            current_val = farmer_data["address"].get(key_name, "")
                            if str(current_val) != new_value:
                                farmer_data["address"][key_name] = new_value
                                updates_made = True
                        else:
                             # Try finding by key name itself if col_name standard not found?
                             if key_name in df.columns:
                                 new_value = row[key_name]
                                 if pd.isna(new_value): new_value = ""
                                 else: new_value = str(new_value).strip()
                                 
                                 current_val = farmer_data["address"].get(key_name, "")
                                 if str(current_val) != new_value:
                                     farmer_data["address"][key_name] = new_value
                                     updates_made = True
                else:
                    status = "Failed: No address data"
                    results.append((index, status, ""))
                    continue

                if not updates_made:
                     # log(f"[Thread {thread_id}] No changes for {farmer_id}")
                     results.append((index, "Skipped: No changes", ""))
                     continue
                
                # PUT
                time.sleep(1) # specified in user example
                
                # requests.put(PUT_API_URL, headers=HEADERS,  files=multipart_data)

                multipart_data = {
                    "dto": (None, json.dumps(farmer_data), "application/json")
                }
                
                put_resp = requests.put(put_url_final, headers=headers, files=multipart_data)
                put_resp.raise_for_status()

                status = "Success"
                response_str = put_resp.text[:600]
                log(f"[Thread {thread_id}] ✅ Success: {farmer_id}")

            except Exception as e:
                status = f"Failed: {str(e)}"
                response_str = str(e)
                log(f"[Thread {thread_id}] ❌ Failed: {farmer_id} - {e}")

            time.sleep(0.5)
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
