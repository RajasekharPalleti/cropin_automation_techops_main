
"""
Updates tags associated with farmers.

Inputs:
Excel file with 'farmer_id' and 'tags' (comma-separated IDs).
"""

import json
import requests
import time
import pandas as pd

from concurrent.futures import ThreadPoolExecutor

def parse_comma_ids(cell):
    """
    Accept input formats like:
      "121,122" or "121"
    Returns list of ints. Empty list for NaN/empty.
    """
    if pd.isna(cell):
        return []
    s = str(cell).strip()
    if s == "":
        return []
    parts = [p.strip() for p in s.split(",") if p.strip() != ""]
    ids = []
    for p in parts:
        try:
            ids.append(int(p))
        except ValueError:
            # ignore non-integer parts
            continue
    return ids

def process_chunk(df_chunk, api_url, token, thread_id, log_callback=None, timeout=30, delay_time=1):
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    headers = {"Authorization": f"Bearer {token}"}
    results = []

    for index, row in df_chunk.iterrows():
        # log(f"[Thread {thread_id}] Processing row index: {index}") # too verbose for websocket maybe?
        
        # User script used iloc positions: 0 -> Farmer ID, 2 -> Tags
        try:
            farmer_id = row.iloc[0]   # Column A: Farmer ID
            raw_tags_cell = row.iloc[2]  # Column C : Farmer Tag IDs
        except IndexError:
             status = "Skipped: Row missing columns"
             results.append((index, status, "IndexError"))
             continue

        status = ""
        response_str = ""

        if pd.isna(farmer_id):
            status = "Skipped: Missing Farmer ID"
            results.append((index, status, response_str))
            continue

        new_ids = parse_comma_ids(raw_tags_cell)
        if not new_ids:
            status = "Skipped: No tag IDs to add"
            results.append((index, status, response_str))
            continue

        try:
            # GET existing farmer
            # Assuming api_url is the base collection URL, e.g. .../farmers
            get_url = f"{api_url}/{farmer_id}"
            get_resp = requests.get(get_url, headers=headers, timeout=timeout)
            get_resp.raise_for_status()
            farmer_json = get_resp.json()

            data = farmer_json.get("data", {})
            existing_tags = data.get("tags", []) or []
            # normalize existing tags to ints when possible
            existing_ints = []
            for t in existing_tags:
                try:
                    existing_ints.append(int(t))
                except Exception:
                    # ignore non-integer existing tags
                    continue

            # determine which IDs to actually add (skip those already present)
            to_add = [i for i in new_ids if i not in existing_ints]
            if not to_add:
                status = "Skipped: All IDs already present"
                results.append((index, status, response_str))
                continue

            # update data["tags"] by appending new ints
            updated_tags = existing_ints + to_add
            data["tags"] = updated_tags
            farmer_json["data"] = data

            # prepare multipart dto and PUT to specific farmer URL
            # Wait, the user script had: requests.put(f"{api_url}", ...) 
            # This looks wrong if api_url is ".../farmers". Usually PUT is to ".../farmers/{id}" OR ".../farmers" if it's a bulk update?
            # User script: requests.put(f"{api_url}", headers=headers, files=multipart, timeout=timeout)
            # The API usually is PUT /farmers to update ONE farmer if the payload contains the ID, or PUT /farmers/{id}.
            # Let's look closely at user script.
            # user script: get_resp = requests.get(f"{api_url}/{farmer_id}", ...)
            # user script: put_resp = requests.put(f"{api_url}", ...)
            # If the user says so, I will stick to it. But it might be updating the *collection*? 
            # Or maybe api_url should include connection? 
            # In Cropin APIs, usually PUT /farmers accepts a multipart DTO for creation/update.
            
            multipart = {"dto": (None, json.dumps(farmer_json), "application/json")}
            put_resp = requests.put(f"{api_url}", headers=headers, files=multipart, timeout=timeout)
            
            if put_resp.status_code in [200, 201, 204]:
                put_resp_json = put_resp.json() if put_resp.content else {}
                # Check for business logic errors in 200 OK responses sometimes
                status = "Success"
                response_str = str(put_resp_json)[:500]
                log(f"[Thread {thread_id}] Farmer {farmer_id} updated, added IDs: {to_add}")
            else:
                 put_resp.raise_for_status() # Trigger except block

        except requests.exceptions.RequestException as e:
            status = f"Failed: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                response_str = f"{e.response.status_code} - {e.response.text}"
            else:
                response_str = str(e)
            log(f"[Thread {thread_id}] Request error for farmer {farmer_id}: {response_str[:100]}")

        time.sleep(delay_time)
        results.append((index, status, response_str))

    return results

def run(input_excel_file, output_excel_file, config, log_callback=None):
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    api_url = config.get("post_api_url")
    token = config.get("token")

    if not api_url:
        log("Error: 'post_api_url' not configured.")
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
    
    # Split into maximum 4 chunks
    max_workers = 4
    chunk_size = (n + max_workers - 1) // max_workers # ceiling division
    
    chunks = []
    for i in range(0, n, chunk_size):
        chunks.append(df.iloc[i:i + chunk_size])
    
    # Adjust workers if fewer chunks
    workers = min(len(chunks), max_workers)
    if workers == 0:
        log("No data to process.")
        return

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

    # Apply results back to DF
    # Results are (index, status, resp)
    for idx, status, resp in all_results:
        df.at[idx, "Status"] = status
        df.at[idx, "Response"] = resp

    log(f"Saving output to {output_excel_file}")
    df.to_excel(output_excel_file, index=False)
    log("Task Completed.")
