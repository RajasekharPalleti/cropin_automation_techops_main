"""
Remove ASSET tags from assets using Excel input.

Inputs:
Excel file with 'Asset ID' and 'Tags' (comma-separated IDs or Names).
"""

import json
import requests
import pandas as pd
import time
import re
import os

# ------------------------------------------------------------
# Normalize tag names (handles spaces & case)
# ------------------------------------------------------------
def normalize_tag_name(name: str) -> str:
    """
    Normalize tag names for consistent comparison.
    """
    return re.sub(r"\s+", " ", str(name).strip().lower())

# ------------------------------------------------------------
# Fetch ASSET tags (Name → ID mapping)
# ------------------------------------------------------------
def fetch_asset_tag_map(token, url):
    """
    Fetch all ASSET tags from the Master Tag API.
    """
    if not url:
        url = "https://cloud.cropin.in/services/master/api/filter?type=ASSET&size=10000"
        
    headers = {"Authorization": f"Bearer {token}"}

    print(f"Fetching tags from: {url}")
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    tag_map = {}
    for tag in response.json():
        if "id" in tag and "name" in tag:
            tag_map[normalize_tag_name(tag["name"])] = tag["id"]

    print(f"✅ Loaded {len(tag_map)} ASSET tags")
    return tag_map

# ------------------------------------------------------------
# Resolve Excel input → Tag IDs
# ------------------------------------------------------------
def resolve_tag_ids(raw_tokens, tag_name_map):
    """
    Resolve tag IDs from Excel input (IDs / Names / Mixed).
    """
    resolved_ids = []
    unresolved = []

    for token in raw_tokens:
        token = str(token).strip()

        if token.isdigit():
            resolved_ids.append(int(token))
        else:
            normalized = normalize_tag_name(token)
            if normalized in tag_name_map:
                resolved_ids.append(tag_name_map[normalized])
            else:
                unresolved.append(token)

    return resolved_ids, unresolved

# ------------------------------------------------------------
# Remove tag IDs from asset response
# ------------------------------------------------------------
def remove_tag_ids(asset_data, tag_ids_to_remove):
    """
    Remove specified tag IDs from asset response.
    """
    tags = asset_data.get("data", {}).get("tags", [])

    if not isinstance(tags, list):
        return asset_data, set()

    original = set(tags)
    remove_set = set(tag_ids_to_remove)

    updated_tags = [t for t in tags if t not in remove_set]
    removed = original - set(updated_tags)

    asset_data["data"]["tags"] = updated_tags
    return asset_data, removed

# ------------------------------------------------------------
# Main Run Function
# ------------------------------------------------------------
def run(input_excel_file, output_excel_file, config, log_callback=None):
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    api_url = config.get("base_api_url", "https://cloud.cropin.in/services/farm/api/assets")
    second_base_api_url = config.get("second_base_api_url", "https://cloud.cropin.in/services/master/api/filter?type=ASSET&size=10000")
    token = config.get("token")

    if not api_url:
        log("Error: 'base_api_url' not configured.")
        return
    if not token:
        log("Error: Authorization token missing.")
        return

    delay_time = float(config.get("delay_time", 0.5))  # seconds, configurable via UI

    # 2. Setup
    log(f"Fetching Tag Map from Master API...")
    try:
        tag_name_map = fetch_asset_tag_map(token, second_base_api_url)
    except Exception as e:
        log(f"❌ Failed to fetch tags: {e}")
        return

    log(f"Reading input file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"Failed to read Excel: {e}")
        return

    # 3. Add columns for output and ensure string type for safety
    for col in ["Status", "Failure Reason"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    req_headers = {"Authorization": f"Bearer {token}"}

    # 4. Process Rows
    total_rows = len(df)
    processed_count = 0
    log(f"Processing {total_rows} rows...")

    for index, row in df.iterrows():
        # Using iloc to match original script's column assumption: index 0 (Asset ID), index 2 (Tags)
        # Column 2 is Asset Name based on original script comments, but tags are fetched from column 3 (index 2)
        # Wait, let me check the original script's row mapping again.
        # original line 163: asset_id = sheet.cell(row, 1).value
        # original line 165: raw_tags = sheet.cell(row, 3).value
        
        asset_id = row.iloc[0] if len(row) > 0 else None
        raw_tags = row.iloc[2] if len(row) > 2 else None

        pending_rows = total_rows - processed_count
        log(f"🔄 Processing row {index+1}/{total_rows} | Processed: {processed_count} | Pending: {pending_rows} | Asset: {asset_id}")

        if pd.isna(asset_id) or pd.isna(raw_tags):
            df.at[index, "Status"] = "Skipped"
            df.at[index, "Failure Reason"] = "Missing Asset ID or Tags"
            continue

        asset_id = str(asset_id).strip()
        cleaned_tags = re.sub(r'[\[\]\'\"]', '', str(raw_tags))
        raw_tokens = [t.strip() for t in cleaned_tags.split(",") if t.strip()]
        tag_ids, _ = resolve_tag_ids(raw_tokens, tag_name_map)

        if not tag_ids:
            df.at[index, "Status"] = "Skipped"
            df.at[index, "Failure Reason"] = "No valid tags found"
            continue

        try:
            # GET Asset
            get_resp = requests.get(f"{api_url}/{asset_id}", headers=req_headers)
            get_resp.raise_for_status()
            asset_data = get_resp.json()

            existing_tags = asset_data.get("data", {}).get("tags", [])
            
            # Convert existing to set of ints if possible
            existing_tags_set = set()
            for t in existing_tags:
                try:
                    existing_tags_set.add(int(t))
                except:
                    pass

            common_tags = existing_tags_set.intersection(set(tag_ids))

            if not common_tags:
                df.at[index, "Status"] = "Skipped"
                df.at[index, "Failure Reason"] = "No tags found to remove"
                continue

            updated_asset, removed_ids = remove_tag_ids(asset_data, tag_ids)

            multipart_data = {
                "dto": (None, json.dumps(updated_asset), "application/json")
            }

            time.sleep(delay_time)

            # PUT Asset update
            put_resp = requests.put(api_url, headers=req_headers, files=multipart_data)
            put_resp.raise_for_status()

            df.at[index, "Status"] = "Success"
            df.at[index, "Failure Reason"] = f"Removed Tag IDs: {', '.join(map(str, removed_ids))}"
            log(f"Row {index + 2}: Asset {asset_id} updated. Removed: {removed_ids}")

        except requests.exceptions.RequestException as e:
            err_msg = str(e)
            if e.response is not None:
                err_msg += f" - {e.response.text}"
            df.at[index, "Status"] = "Failed"
            df.at[index, "Failure Reason"] = err_msg
            log(f"Row {index + 2}: Failed - {err_msg[:100]}")

        processed_count += 1
        time.sleep(delay_time)

    # Save to OUTPUT file
    try:
        df.to_excel(output_excel_file, index=False)
        log(f"📁 Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"❌ Error saving output: {e}")
