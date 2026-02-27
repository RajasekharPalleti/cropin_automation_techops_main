"""
Updates additional attributes for assets based on configured keys.

Inputs:
Excel file with 'asset_id' and columns matching configured attribute keys.
"""
import pandas as pd
import requests
import json
import time

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    token = config.get("token")
    if not token:
        log("❌ No token provided in configuration.")
        return

    # API URL
    api_url = config.get("post_api_url")
    if not api_url:
        api_url = "https://cloud.cropin.in/services/farm/api/assets"
        log(f"Using default Asset API URL: {api_url}")
    api_url = api_url.rstrip('/')

    delay_time = float(config.get("delay_time", 0.2))  # seconds, configurable via UI

    # Attribute Keys from Config
    # config['attr_keys'] should be a list [key1, key2, key3, key4]
    attr_keys = config.get("attr_keys", [])
    
    # Filter valid keys and keep their index (0-based) to map to Excel columns
    # We map keys[0] -> additional_attribute_1, keys[1] -> additional_attribute_2, etc.
    valid_keys_map = {} # {index: key_name}
    for i, key in enumerate(attr_keys):
        if key and key.strip():
            valid_keys_map[i] = key.strip()

    if not valid_keys_map:
        log("⚠️ No Attribute Keys configured! Please enter at least one key in the UI.")
        # Proceeding might be useless, but let's let looking for columns fail naturally or warn.

    headers = {
        "Authorization": f"Bearer {token}"
    }

    log("📘 Loading Excel file...")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"Error reading Excel file: {e}")
        return

    # Ensure status column
    if "Status" not in df.columns:
        df["Status"] = ""

    # Check for asset_id
    if "asset_id" not in df.columns:
        # Fallback to col 1 if named differently
        log("⚠️ 'asset_id' column not found. Assuming first column is Asset ID.")
        # We can rename first column for easier access
        df.rename(columns={df.columns[0]: 'asset_id'}, inplace=True)

    log(f"🔄 Starting processing {len(df)} assets...")

    for index, row in df.iterrows():
        asset_id = str(row['asset_id']).strip()
        if not asset_id or asset_id.lower() == 'nan':
             log(f"Skipping empty row {index + 1}")
             continue
             
        log(f"Processing Row {index + 1}: Asset ID {asset_id}")

        try:
            # 1. GET Asset
            get_resp = requests.get(f"{api_url}/{asset_id}", headers=headers)
            get_resp.raise_for_status()
            asset_data = get_resp.json()
            
            # Prepare updates
            updates_made = False
            
            if "data" in asset_data and isinstance(asset_data["data"], dict):
                # Iterate over configured keys
                for key_idx, key_name in valid_keys_map.items():
                    # Map to Excel column: additional_attribute_{key_idx + 1}
                    col_name = f"additional_attribute_{key_idx + 1}"
                    
                    if col_name in df.columns:
                        new_value = row[col_name]
                        # Handle NaNs
                        if pd.isna(new_value):
                            new_value = ""
                        else:
                            new_value = str(new_value).strip()
                            
                        # Update JSON
                        # Ensure key exists or create it
                        if key_name not in asset_data["data"] or asset_data["data"][key_name] is None:
                             asset_data["data"][key_name] = ""
                        
                        asset_data["data"][key_name] = new_value
                        updates_made = True
                        log(f"   -> Setting {key_name} = '{new_value}'")
                    else:
                        log(f"   ⚠️ Column '{col_name}' missing in Excel for key '{key_name}'")

            else:
                 msg = "Failed: No valid 'data' object in response"
                 df.at[index, "Status"] = msg
                 log(msg)
                 continue

            if not updates_made:
                log("   ⚠️ No attributes updated (check config or columns). Skipping PUT.")
                df.at[index, "Status"] = "Skipped: No changes"
                continue

            # 2. PUT Update
            time.sleep(delay_time)
            
            # Application/json Multipart
            multipart_data = {
                "dto": (None, json.dumps(asset_data), "application/json")
            }
            
            put_resp = requests.put(api_url, headers=headers, files=multipart_data)
            put_resp.raise_for_status()
            
            df.at[index, "Status"] = "Success"
            log(f"✅ Successfully updated {asset_id}")

        except Exception as e:
            err_msg = str(e)
            df.at[index, "Status"] = f"Failed: {err_msg}"
            log(f"❌ Failed for {asset_id}: {err_msg}")

        time.sleep(delay_time)

    try:
        df.to_excel(output_excel_file, index=False)
        log(f"📁 Execution complete. Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"Error saving output file: {e}")
