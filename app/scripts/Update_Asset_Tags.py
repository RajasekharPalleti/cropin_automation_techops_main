
"""
Updates tags associated with assets.

Inputs:
Excel file with 'asset_id' and 'tags' (list or comma-separated).
"""

import json
import requests
import time
import pandas as pd

from concurrent.futures import ThreadPoolExecutor
import ast

def parse_tags(raw):
    """Accept: 122  |  123,231  |  [123,231,456]"""
    if raw is None:
        return []
    import pandas as pd
    if isinstance(raw, float) and pd.isna(raw):
        return []
    s = str(raw).strip().strip("[]").strip()
    if not s:
        return []
    parts = [p.strip() for p in s.split(",") if p.strip()]
    result = []
    for p in parts:
        try:
            result.append(int(float(p)))
        except ValueError:
            pass
    return result

def process_chunk(df_chunk, api_url, token, thread_id, log_callback=None, timeout=30, delay_time=1):
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    headers = {"Authorization": f"Bearer {token}"}
    results = []

    for index, row in df_chunk.iterrows():
        # log(f"[Thread {thread_id}] Processing row index: {index}") # Optional verbose log

        try:
            asset_id = row.iloc[0]  # Column A: Asset ID
            asset_name = row.iloc[1] if len(row) > 1 else "" # Column B: Asset Name
            raw_tags = row.iloc[2]  # Column C: Tags, Example: " [1, 2, 3] "
        except IndexError:
             status = "Skipped: Row missing columns"
             results.append((index, status, "IndexError"))
             continue

        row_num = index + 2

        status = ""
        response_str = ""

        asset_tags = parse_tags(raw_tags)

        if pd.isna(asset_id):
            status = "Skipped: Missing Asset ID"
            results.append((index, status, response_str))
            continue

        try:
            # log(f"[Thread {thread_id}] Getting asset for: {asset_id}")
            get_response = requests.get(f"{api_url}/{asset_id}", headers=headers, timeout=timeout)
            get_response.raise_for_status()
            asset_data = get_response.json()

            if "data" in asset_data and isinstance(asset_data["data"], dict):
                existing_tags = asset_data["data"].get("tags", [])
                if existing_tags is None:
                    existing_tags = []
                
                # Merge logic: Append new tags if they don't exist
                # Logic: Keep all existing, add new ones unique
                # Assuming simple scalars (int/str) or check equality
                
                # Normalize types to avoid duplicates like "123" vs 123 if needed
                # But assets tags can be whatever. Let's assume standard equality check.
                
                updated_tags = list(existing_tags)
                to_add = []
                for tag in asset_tags:
                    if tag not in existing_tags:
                        to_add.append(tag)
                        updated_tags.append(tag)
                
                if not to_add:
                    status = "Skipped: All IDs already present"
                    results.append((index, status, response_str))
                    continue

                asset_data["data"]["tags"] = updated_tags
            else:
                status = "Failed: No data property in response"
                results.append((index, status, response_str))
                continue

            time.sleep(delay_time)

            multipart_data = {
                "dto": (None, json.dumps(asset_data), "application/json")
            }

            # PUT to base URL as per user code: requests.put(api_url, ...)
            # This implies api_url is the collection resource, and the DTO contains the ID or the update is handled via DTO.
            # In user code: requests.put(api_url, ...)
            put_response = requests.put(api_url, headers=headers, files=multipart_data, timeout=timeout)
            
            if put_response.status_code in [200, 201, 204]:
                status = "Success"
                response_str = put_response.text[:500]
                log(f"[Row {row_num}] Updated Asset '{asset_name}' ({asset_id})")
            else:
                status = f"Failed: {put_response.status_code}"
                response_str = put_response.text[:500]
                log(f"[Row {row_num}] Failed to update Asset '{asset_name}' ({asset_id}): {put_response.status_code}")

        except requests.exceptions.RequestException as e:
            status = f"Failed: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                response_str = f"{e.response.status_code} - {e.response.text}"
            else:
                response_str = str(e)
            log(f"[Row {row_num}] Error for Asset '{asset_name}' ({asset_id}): {response_str[:100]}")

        time.sleep(delay_time)
        results.append((index, status, response_str))

    return results

def run(input_excel_file, output_excel_file, config, log_callback=None):
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    api_url = config.get("base_api_url")
    token = config.get("token")
    worker_count = int(config.get("worker_count", 4))

    if not api_url:
        log("Error: 'base_api_url' not configured.")
        return
    if not token:
        log("Error: Authorization token missing.")
        return

    delay_time = float(config.get("delay_time", 1))  # seconds, configurable via UI

    log(f"Reading input file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"Failed to read Excel: {e}")
        return

    if "Status" not in df.columns:
        df["Status"] = ""
    if "Response" not in df.columns:
        df["Response"] = ""

    n = len(df)
    log(f"Total rows to process: {n}")
    
    # Split into configured chunks
    max_workers = worker_count
    chunk_size = (n + max_workers - 1) // max_workers # ceiling division
    
    chunks = []
    # If n=0, this loop won't run, check n>0
    if n > 0:
        for i in range(0, n, chunk_size):
            chunks.append(df.iloc[i:i + chunk_size])
    else:
        log("No data to process.")
        df.to_excel(output_excel, index=False)
        return

    # Adjust workers
    workers = min(len(chunks), max_workers)
    
    log(f"Starting execution with {workers} threads...")

    all_results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = []
        for i, chunk in enumerate(chunks):
            futures.append(ex.submit(process_chunk, chunk, api_url, token, i+1, log_callback, delay_time=delay_time))
        
        for f in futures:
            try:
                all_results.extend(f.result())
            except Exception as e:
                log(f"Thread failed: {e}")

    # Apply results
    for idx, status, resp in all_results:
        df.at[idx, "Status"] = status
        df.at[idx, "Response"] = resp

    log(f"Saving output to {output_excel_file}")
    df.to_excel(output_excel_file, index=False)
    log("Task Completed.")
