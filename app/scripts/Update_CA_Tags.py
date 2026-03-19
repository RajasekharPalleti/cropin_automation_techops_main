
"""
Updates tags associated with croppable areas (CAs).

Inputs:
Excel file with 'ca_id' and 'tags' (list or comma-separated).
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

def process_chunk(df_chunk, api_url, token, thread_id, shared_stats, log_callback=None, timeout=30, delay_time=1):
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    headers = {"Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
    }
    results = []

    for index, row in df_chunk.iterrows():

        try:
            ca_id = row.iloc[0]  # Column A: CA ID
            ca_name = row.iloc[1] if len(row) > 1 else "" # Column B: CA Name
            raw_tags = row.iloc[2]  # Column C: Tags, Example: " [1, 2, 3] "
        except IndexError:
             status = "Skipped: Row missing columns"
             results.append((index, status, "IndexError"))
             continue

        row_num = index + 2

        status = ""
        response_str = ""

        ca_tags = parse_tags(raw_tags)

        if pd.isna(ca_id):
            status = "Skipped: Missing CA ID"
            results.append((index, status, response_str))
            continue

        try:
            try:
                # GET
                get_response = requests.get(f"{api_url}/{ca_id}", headers=headers, timeout=timeout)
                get_response.raise_for_status()
                ca_data = get_response.json()

                if "data" in ca_data and isinstance(ca_data["data"], dict):
                    existing_tags = ca_data["data"].get("tags", [])
                    if existing_tags is None:
                        existing_tags = []

                    # Merge logic: Append new tags if they don't exist
                    updated_tags = list(existing_tags)
                    to_add = []
                    for tag in ca_tags:
                        if tag not in existing_tags:
                            to_add.append(tag)
                            updated_tags.append(tag)

                    if not to_add:
                        status = "Skipped: All IDs already present"
                        results.append((index, status, response_str))
                        continue
                    else:
                        ca_data["data"]["tags"] = updated_tags
                        
                        time.sleep(delay_time)

                        put_response = requests.put(api_url, headers=headers, json=ca_data, timeout=timeout)

                        if put_response.status_code in [200, 201, 204]:
                            status = "Success"
                            response_str = put_response.text[:500]
                            log(f"[Row {row_num}] Updated CA '{ca_name}' ({ca_id})")
                        else:
                            status = f"Failed: {put_response.status_code}"
                            response_str = put_response.text[:500]
                            log(f"[Row {row_num}] Failed to update CA '{ca_name}' ({ca_id}): {put_response.status_code}")
                else:
                    status = "Failed: No data property in response"
                    results.append((index, status, response_str))

            except requests.exceptions.RequestException as e:
                status = f"Failed: {str(e)}"
                if hasattr(e, 'response') and e.response is not None:
                    response_str = f"{e.response.status_code} - {e.response.text}"
                else:
                    response_str = str(e)
                log(f"[Row {row_num}] Error for CA '{ca_name}' ({ca_id}): {response_str[:100]}")

            time.sleep(delay_time)
            results.append((index, status, response_str))
        finally:
            if shared_stats:
                with shared_stats["lock"]:
                    shared_stats["processed"] += 1
                    pending = shared_stats["total"] - shared_stats["processed"]
                    log(f"[Thread {thread_id}] Processed: {shared_stats['processed']}/{shared_stats['total']} | Pending: {pending} | CA: {ca_id}")

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

    # Ensure Status/Response columns are explicitly cast to string to avoid TypeError
    if "Status" not in df.columns:
        df["Status"] = ""
    df["Status"] = df["Status"].fillna("").astype(str)
    
    if "Response" not in df.columns:
        df["Response"] = ""
    df["Response"] = df["Response"].fillna("").astype(str)

    n = len(df)
    log(f"Total rows to process: {n}")

    # Split into configured chunks
    max_workers = worker_count
    chunk_size = (n + max_workers - 1) // max_workers  # ceiling division

    chunks = []
    if n > 0:
        for i in range(0, n, chunk_size):
            chunks.append(df.iloc[i:i + chunk_size])
    else:
        log("No data to process.")
        df.to_excel(output_excel_file, index=False)
        return

    # Adjust workers
    workers = min(len(chunks), max_workers)

    import threading
    shared_stats = {
        "total": n,
        "processed": 0,
        "lock": threading.Lock()
    }

    all_results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = []
        for i, chunk in enumerate(chunks):
            futures.append(ex.submit(process_chunk, chunk, api_url, token, i+1, shared_stats, log_callback, delay_time=delay_time))

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
