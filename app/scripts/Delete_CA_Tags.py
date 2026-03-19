"""
Remove CA tags from croppable areas using Excel input.

Inputs:
Excel file with 'CA_id', 'CA_name', and 'Tags IDs' (comma-separated IDs or Names).
"""

import json
import requests
import pandas as pd
import time
import re

# ------------------------------------------------------------
# Normalize tag names (handles spaces & case)
# ------------------------------------------------------------
def normalize_tag_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip().lower())

# ------------------------------------------------------------
# Fetch CA tags (Name → ID mapping)
# ------------------------------------------------------------
def fetch_ca_tag_map(token, url):
    if not url:
        url = "https://cloud.cropin.in/services/master/api/filter?type=CA&size=10000"
        
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
# Main Run Function
# ------------------------------------------------------------
def run(input_excel_file, output_excel_file, config, log_callback=None):
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    # 1. Parse Config
    api_url = config.get("base_api_url", "https://cloud.cropin.in/services/farm/api/croppable-areas")
    second_base_api_url = config.get("second_base_api_url", "https://cloud.cropin.in/services/master/api/filter?type=CA&size=10000")
    token = config.get("token")

    if not api_url:
        log("Error: API URL not configured.")
        return
    if not token:
        log("Error: Authorization token missing.")
        return

    delay_time = float(config.get("delay_time", 0.5))  # seconds, configurable via UI

    # 2. Setup
    log(f"Fetching Tag Map from Master API...")
    try:
        tag_name_map = fetch_ca_tag_map(token, second_base_api_url)
        log(f"✅ Loaded {len(tag_name_map)} CA tags")
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
        # Using iloc to match original script's column assumption: index 0 (CA_id), index 2 (Tags IDs)
        ca_id = row.iloc[0] if len(row) > 0 else None
        raw_tags = row.iloc[2] if len(row) > 2 else None

        pending_rows = total_rows - processed_count
        log(f"🔄 Processing row {index+1}/{total_rows} | Processed: {processed_count} | Pending: {pending_rows} | CA: {ca_id}")

        if pd.isna(ca_id) or pd.isna(raw_tags):
            df.at[index, "Status"] = "Skipped"
            df.at[index, "Failure Reason"] = "Missing CA_id or Tags IDs"
            continue

        ca_id = str(ca_id).strip()
        cleaned_tags = re.sub(r'[\[\]\'\"]', '', str(raw_tags))
        raw_tokens = [t.strip() for t in cleaned_tags.split(",") if t.strip()]
        tag_ids, unresolved = resolve_tag_ids(raw_tokens, tag_name_map)

        if unresolved:
            log(f"Warning mapping tags for CA {ca_id}: Could not resolve '{', '.join(unresolved)}'")

        if not tag_ids:
            df.at[index, "Status"] = "Skipped"
            df.at[index, "Failure Reason"] = "No valid tags found matching system records"
            continue

        try:
            # First, fetch the existing CA
            get_resp = requests.get(f"{api_url}/{ca_id}", headers=req_headers)
            get_resp.raise_for_status()
            ca_data = get_resp.json()

            # Ensure data wrapper exists
            if "data" not in ca_data:
                ca_data["data"] = {}
                
            existing_tags = ca_data["data"].get("tags", [])
            
            existing_tag_ids = set()
            for t in existing_tags:
                try:
                    existing_tag_ids.add(int(t))
                except:
                    pass

            to_remove_set = set(tag_ids)
            intersection = existing_tag_ids.intersection(to_remove_set)

            if not intersection:
                df.at[index, "Status"] = "Skipped"
                df.at[index, "Failure Reason"] = "No specified tags exist on this CA to remove"
                continue

            # Remove the specified tags from the active set
            final_tag_ids = existing_tag_ids - to_remove_set
            
            # Format as expected by Cropin CA PUT API (list of ints)
            ca_data["data"]["tags"] = list(final_tag_ids)
            
            # Update the CA
            put_resp = requests.put(api_url, headers=req_headers, json=ca_data)
            put_resp.raise_for_status()

            df.at[index, "Status"] = "Success"
            df.at[index, "Failure Reason"] = f"Removed Tag IDs: {', '.join(map(str, intersection))}"
            log(f"Row {index + 2}: CA {ca_id} updated. Removed: {intersection}")

        except requests.exceptions.RequestException as e:
            err_msg = str(e)
            if e.response is not None:
                err_msg += f" - {e.response.text}"
            df.at[index, "Status"] = "Failed"
            df.at[index, "Failure Reason"] = err_msg
            log(f"Row {index + 2}: Failed - {err_msg[:100]}")

        # Throttle delay
        processed_count += 1
        time.sleep(delay_time)

    # 5. Save Output
    try:
        df.to_excel(output_excel_file, index=False)
        log(f"✅ Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"❌ Error saving output: {e}")
