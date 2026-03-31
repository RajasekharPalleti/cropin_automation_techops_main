"""
Delete tasks via bulk delete API in configurable batches of Task IDs (no CA grouping, no verification).
Captures the raw API response for each batch and stores it against every processed Task ID row.
Batch size is configurable from the UI (max 100, default 100).

Inputs:
Excel file with 'Task_Id' column only (one task ID per row).
"""

import requests
import pandas as pd
import time
import json

# Author: Rajasekhar Palleti

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    api_url_delete = config.get("base_api_url", "https://cloud.cropin.in/services/farm/api/tasks/bulk")
    token = config.get("token")
    delay_time = float(config.get("delay_time", 1.0))

    # Batch size configurable from UI, capped at 100
    batch_size = int(config.get("batch_size", 100))
    if batch_size < 1:
        batch_size = 1

    if not token:
        log("Error: Authorization token missing.")
        return

    req_headers = {"Authorization": f"Bearer {token}"}

    log(f"Reading input file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"Failed to read Excel: {e}")
        return

    # Ensure tracking columns with proper type safety
    for col in ["Status", "Response"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    # Identify Task_Id column
    task_id_col = None
    for possible in ["Task_Id", "Task_Ids", "task_id"]:
        if possible in df.columns:
            task_id_col = possible
            break
    if not task_id_col:
        task_id_col = df.columns[0]
        log(f"Warning: Could not find 'Task_Id' header. Falling back to Column: {task_id_col}")

    total_rows = len(df)
    processed_count = 0
    skipped_count = 0
    log(f"Total rows: {total_rows} | Batch size: {batch_size}")
    log("Processing tasks in flat batches...")

    # Collect all valid rows (Task_Id only)
    all_items = []

    for index, row in df.iterrows():
        task_id_raw = row[task_id_col]

        if pd.isna(task_id_raw):
            df.at[index, "Status"] = "Skipped"
            df.at[index, "Response"] = "Missing Task_Id"
            skipped_count += 1
            continue

        task_id_str = str(int(float(task_id_raw))).strip()
        all_items.append((index, task_id_str))

    total_valid = len(all_items)
    total_batches = (total_valid + batch_size - 1) // batch_size if total_valid > 0 else 0
    log(f"Valid rows to process: {total_valid} | Skipped: {skipped_count}")

    # Process each batch
    for batch_num_idx, i in enumerate(range(0, total_valid, batch_size), start=1):
        batch = all_items[i:i + batch_size]
        batch_task_ids = [item[1] for item in batch]
        clean_task_ids_str = ",".join(batch_task_ids)
        pending_total = total_valid - processed_count

        log(f"[Batch {batch_num_idx}/{total_batches}] Deleting {len(batch)} tasks... "
            f"| Row {processed_count + 1} to {processed_count + len(batch)} of {total_valid} "
            f"| Total Processed: {processed_count} | Total Pending: {pending_total}")

        try:
            delete_url = f"{api_url_delete}?ids={clean_task_ids_str}"
            del_resp = requests.delete(delete_url, headers=req_headers)

            # Capture raw response text
            try:
                response_body = json.dumps(del_resp.json(), separators=(',', ':'))
            except Exception:
                response_body = del_resp.text or f"HTTP {del_resp.status_code}"

            if del_resp.ok:
                log(f"[Batch {batch_num_idx}] Success | Response: {response_body[:200]}")
                for idx, tid in batch:
                    df.at[idx, "Status"] = "Success"
                    df.at[idx, "Response"] = response_body
            else:
                log(f"[Batch {batch_num_idx}] API returned HTTP {del_resp.status_code} | Response: {response_body[:200]}")
                for idx, tid in batch:
                    df.at[idx, "Status"] = "Failed"
                    df.at[idx, "Response"] = f"HTTP {del_resp.status_code} - {response_body}"

        except requests.exceptions.RequestException as e:
            err_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    err_msg += f" - {e.response.text}"
                except Exception:
                    pass
            log(f"[Batch {batch_num_idx}] Request Failed - {err_msg[:200]}")
            for idx, tid in batch:
                df.at[idx, "Status"] = "Failed"
                df.at[idx, "Response"] = err_msg

        # Update counters and throttle
        processed_count += len(batch)
        time.sleep(delay_time)

    log(f"All batches done. Processed: {processed_count} | Skipped: {skipped_count}")

    # Save Output
    try:
        df.to_excel(output_excel_file, index=False)
        log(f"✅ Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"❌ Error saving output: {e}")
