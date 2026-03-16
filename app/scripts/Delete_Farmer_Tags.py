"""
Remove FARMER tags from farmers using Excel input.

Inputs:
Excel file with 'Farmer ID' and 'Tags' (comma-separated IDs or Names).
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
    return re.sub(r"\s+", " ", str(name).strip().lower())

# ------------------------------------------------------------
# Fetch FARMER tags (Name → ID mapping)
# ------------------------------------------------------------
def fetch_farmer_tag_map(token, url):
    if not url:
        url = "https://cloud.cropin.in/services/master/api/filter?type=FARMER&size=10000"
        
    headers = {"Authorization": f"Bearer {token}"}

    print(f"Fetching tags from: {url}")
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    tag_map = {}
    for tag in response.json():
        if "id" in tag and "name" in tag:
            tag_map[normalize_tag_name(tag["name"])] = tag["id"]

    return tag_map

# ------------------------------------------------------------
# Resolve Excel input → Tag IDs
# ------------------------------------------------------------
def resolve_tag_ids(raw_tokens, tag_name_map):
    resolved_ids = []
    unresolved = []

    for token in raw_tokens:
        token = str(token).strip()

        if token.isdigit():
            resolved_ids.append(int(float(token)))
        else:
            normalized = normalize_tag_name(token)
            if normalized in tag_name_map:
                resolved_ids.append(tag_name_map[normalized])
            else:
                unresolved.append(token)

    return resolved_ids, unresolved

# ------------------------------------------------------------
# Remove tag IDs from farmer response
# ------------------------------------------------------------
def remove_tag_ids(farmer_data, tag_ids_to_remove):
    tags = farmer_data.get("data", {}).get("tags", [])

    if not isinstance(tags, list):
        return farmer_data, set()

    original = set(tags)
    remove_set = set(tag_ids_to_remove)

    updated_tags = [t for t in tags if t not in remove_set]
    removed = original - set(updated_tags)

    farmer_data["data"]["tags"] = updated_tags
    return farmer_data, removed

# ------------------------------------------------------------
# Main Run Function
# ------------------------------------------------------------
def run(input_excel_file, output_excel_file, config, log_callback=None):
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    # 1. Parse Config
    api_url = config.get("base_api_url", "https://cloud.cropin.in/services/farm/api/farmers")
    second_base_api_url = config.get("second_base_api_url", "https://cloud.cropin.in/services/master/api/filter?type=FARMER&size=10000")
    token = config.get("token")

    if not api_url:
        log("Error: 'base_api_url' not configured.")
        return
    if not token:
        log("Error: Authorization token missing.")
        return

    delay_time = float(config.get("delay_time", 0.5))  # seconds, configurable via UI

    # 3. Fetch Tag Mapping (Name -> ID)
    log("🔄 Fetching tag mapping from master API...")
    try:
        tag_name_map = fetch_farmer_tag_map(token, second_base_api_url)
        log(f"✅ Loaded {len(tag_name_map)} FARMER tags")
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
    log(f"Processing {total_rows} rows...")

    for index, row in df.iterrows():
        # Using iloc to match original script's column assumption: index 0 (Farmer ID), index 2 (Tags)
        farmer_id = row.iloc[0] if len(row) > 0 else None
        raw_tags = row.iloc[2] if len(row) > 2 else None

        if pd.isna(farmer_id) or pd.isna(raw_tags):
            df.at[index, "Status"] = "Skipped"
            df.at[index, "Failure Reason"] = "Missing Farmer ID or Tags"
            continue

        farmer_id = str(farmer_id).strip()
        cleaned_tags = re.sub(r'[\[\]\'\"]', '', str(raw_tags))
        raw_tokens = [t.strip() for t in cleaned_tags.split(",") if t.strip()]
        tag_ids, _ = resolve_tag_ids(raw_tokens, tag_name_map)

        if not tag_ids:
            df.at[index, "Status"] = "Skipped"
            df.at[index, "Failure Reason"] = "No valid tags found"
            continue

        try:
            # GET /farmers/{id}
            get_resp = requests.get(f"{api_url}/{farmer_id}", headers=req_headers)
            get_resp.raise_for_status()
            farmer_data = get_resp.json()

            existing_tags = farmer_data.get("data", {}).get("tags", [])
            
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

            updated_farmer, removed_ids = remove_tag_ids(farmer_data, tag_ids)

            multipart_data = {
                "dto": (None, json.dumps(updated_farmer), "application/json")
            }
            
            # PUT to base URL
            put_resp = requests.put(api_url, headers=req_headers, files=multipart_data)
            put_resp.raise_for_status()

            df.at[index, "Status"] = "Success"
            df.at[index, "Failure Reason"] = f"Removed Tag IDs: {', '.join(map(str, removed_ids))}"
            log(f"Row {index + 2}: Farmer {farmer_id} updated. Removed: {removed_ids}")

        except requests.exceptions.RequestException as e:
            err_msg = str(e)
            if e.response is not None:
                err_msg += f" - {e.response.text}"
            df.at[index, "Status"] = "Failed"
            df.at[index, "Failure Reason"] = err_msg
            log(f"Row {index + 2}: Failed - {err_msg[:100]}")

        # Basic rate limiting
        time.sleep(delay_time)

    # 5. Save Output
    try:
        df.to_excel(output_excel_file, index=False)
        log(f"✅ Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"❌ Error saving output: {e}")
