"""
Adds existing assets to a project and validates/converts them to Croppable Areas.
Groups assets by Project ID, batches them, and processes them using multithreading.

Author: Rajasekhar Palleti

Inputs:
Excel file with 'Asset ID' and 'Project ID' columns.
"""
import pandas as pd
import requests
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode("ascii", errors="replace").decode("ascii"))

    # ================= CONFIG ================= #
    token = config.get("token")
    if not token:
        log("❌ No token provided in configuration.")
        return

    api_url = config.get("base_api_url")
    if not api_url:
        api_url = "https://cloud.cropin.in/services/farm/api/projects"
        log(f"Using default Projects API URL: {api_url}")
    api_url = api_url.rstrip('/')

    MAX_WORKERS = int(config.get("worker_count", 2))
    delay_time = float(config.get("delay_time", 1.0))
    BATCH_SIZE = int(config.get("batch_size", 100))
    # ========================================== #

    # 2. Load Excel File
    log(f"📂 Loading input Excel file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
        # Remove unnamed columns
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    # 3. Detect column names from Excel
    # Asset ID column
    asset_col = next((c for c in df.columns if c.strip().lower() == "asset id"), None)
    if not asset_col and len(df.columns) > 0:
        asset_col = df.columns[0]
    if not asset_col:
        log("❌ Could not identify 'Asset ID' column.")
        return
    log(f"ℹ️ Found Asset ID column: '{asset_col}'")

    # Project ID column
    project_col = next((c for c in df.columns if c.strip().lower() == "project id"), None)
    if not project_col and len(df.columns) > 1:
        project_col = df.columns[1]
    if not project_col:
        log("❌ Could not identify 'Project ID' column.")
        return
    log(f"ℹ️ Found Project ID column: '{project_col}'")

    # 4. Ensure output columns exist and are string-safe (Pandas Type Safety)
    for col in ["Project Asset ID", "Croppable Area ID", "Status", "Response"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    total_rows = len(df)
    already_done = df[df['Status'].str.strip().str.lower() == 'success'].shape[0]
    log(f"📊 Total rows: {total_rows} | Already Executed: {already_done} | Pending: {total_rows - already_done}")

    # Filter pending rows for resume support
    pending_df = df[df['Status'].str.strip().str.lower() != 'success']
    if pending_df.empty:
        log("✅ All rows are already processed successfully. Nothing to execute.")
        return

    grouped = pending_df.groupby(project_col)

    df_lock = threading.Lock()
    processed_count = already_done
    processed_lock = threading.Lock()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Thread sub-batch processing function
    def process_sub_batch(batch_df, proj_id_clean, thread_id):
        nonlocal processed_count
        asset_ids = []
        row_indices = []

        for idx, row in batch_df.iterrows():
            raw_asset_id = row.get(asset_col)
            if pd.isna(raw_asset_id) or str(raw_asset_id).strip() == '':
                continue
            try:
                asset_id = int(float(str(raw_asset_id).strip()))
                asset_ids.append(asset_id)
                row_indices.append(idx)
            except ValueError:
                log(f"[Thread {thread_id}] ⚠️ Invalid Asset ID: '{raw_asset_id}' at row {idx+2}")
                with df_lock:
                    df.at[idx, "Status"] = "Failed"
                    df.at[idx, "Response"] = f"Invalid Asset ID: {raw_asset_id}"

        if not asset_ids:
            return

        log(f"[Thread {thread_id}] 🔄 Adding {len(asset_ids)} assets to project {proj_id_clean}...")

        # API 1: Add assets to project
        url1 = f"{api_url}/{proj_id_clean}/probable-assets"
        project_asset_ids = []

        try:
            resp1 = requests.post(url1, headers=headers, json=asset_ids)
            if resp1.status_code not in [200, 201]:
                log(f"[Thread {thread_id}] ❌ API 1 Failed: HTTP {resp1.status_code} - {resp1.text[:300]}")
                with df_lock:
                    for idx in row_indices:
                        df.at[idx, "Status"] = f"API 1 Failed: {resp1.status_code}"
                        df.at[idx, "Response"] = resp1.text[:500]
                return

            resp_json = resp1.json()
            project_asset_ids = resp_json.get("projectAssetIds", [])
            
            if not project_asset_ids:
                log(f"[Thread {thread_id}] ⚠️ API 1 returned no projectAssetIds.")
                with df_lock:
                    for idx in row_indices:
                        df.at[idx, "Status"] = "API 1 Failed"
                        df.at[idx, "Response"] = "No projectAssetIds returned in response."
                return

            with df_lock:
                for idx, p_asset_id in zip(row_indices, project_asset_ids):
                    df.at[idx, "Project Asset ID"] = str(p_asset_id)

            log(f"[Thread {thread_id}] ✅ Added to project. projectAssetIds count: {len(project_asset_ids)}")

        except Exception as e:
            log(f"[Thread {thread_id}] ❌ Exception during API 1: {e}")
            with df_lock:
                for idx in row_indices:
                    df.at[idx, "Status"] = "API 1 Error"
                    df.at[idx, "Response"] = str(e)
            return

        # Sleep/delay between the two API calls as requested
        time.sleep(delay_time)

        # API 2: Validate and convert to CAs
        url2 = f"{api_url}/{proj_id_clean}/self-validate-project-assets?cloneFlag=false"
        log(f"[Thread {thread_id}] 🔄 Validating and converting {len(project_asset_ids)} assets for project {proj_id_clean}...")

        try:
            resp2 = requests.post(url2, headers=headers, json=project_asset_ids)
            if resp2.status_code not in [200, 201]:
                log(f"[Thread {thread_id}] ❌ API 2 Failed: HTTP {resp2.status_code} - {resp2.text[:300]}")
                with df_lock:
                    for idx in row_indices:
                        df.at[idx, "Status"] = f"API 2 Failed: {resp2.status_code}"
                        df.at[idx, "Response"] = resp2.text[:500]
                return

            resp_json2 = resp2.json()
            croppable_area_ids = resp_json2.get("croppableAreaIds", [])

            with df_lock:
                for i, idx in enumerate(row_indices):
                    if i < len(croppable_area_ids):
                        df.at[idx, "Croppable Area ID"] = str(croppable_area_ids[i])
                        df.at[idx, "Status"] = "Success"
                        df.at[idx, "Response"] = "Successfully added and converted to Croppable Area."
                    else:
                        df.at[idx, "Status"] = "Success (No CA ID)"
                        df.at[idx, "Response"] = "Successfully added, but no Croppable Area ID returned for this row."

            log(f"[Thread {thread_id}] ✅ Validation & Conversion finished. CAs created: {len(croppable_area_ids)}")

        except Exception as e:
            log(f"[Thread {thread_id}] ❌ Exception during API 2: {e}")
            with df_lock:
                for idx in row_indices:
                    df.at[idx, "Status"] = "API 2 Error"
                    df.at[idx, "Response"] = str(e)

        # Track progress and sleep
        with processed_lock:
            processed_count += len(row_indices)
            pending_rows = total_rows - processed_count
            log(f"📊 Processed: {processed_count}/{total_rows} | Pending: {pending_rows}")

        time.sleep(delay_time)

    # Process each unique project group sequentially
    for proj_id, group_df in grouped:
        if pd.isna(proj_id) or str(proj_id).strip() == '':
            log("⚠️ Skipping rows with empty Project ID.")
            continue

        try:
            proj_id_clean = str(int(float(str(proj_id).strip())))
        except ValueError:
            log(f"⚠️ Skipping rows with invalid Project ID '{proj_id}'.")
            continue

        log(f"🚀 Starting Project ID: {proj_id_clean} | Pending rows: {len(group_df)}")

        # Split into sub-batches of BATCH_SIZE
        sub_batches = [group_df.iloc[i:i + BATCH_SIZE] for i in range(0, len(group_df), BATCH_SIZE)]
        actual_workers = min(len(sub_batches), MAX_WORKERS)

        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
            futures = [
                executor.submit(process_sub_batch, batch, proj_id_clean, thread_id + 1)
                for thread_id, batch in enumerate(sub_batches)
            ]
            for future in futures:
                try:
                    future.result()
                except Exception as ex:
                    log(f"❌ Error in thread pool worker: {ex}")

        log(f"⏳ Sleeping for {delay_time} seconds before starting the next Project ID...")
        time.sleep(delay_time)

    # Save Excel once at the end
    log("💾 Writing results back to Excel...")
    try:
        df.to_excel(output_excel_file, index=False)
        log(f"🎯 Execution completed. Output spreadsheet saved to: {output_excel_file}")
    except Exception as e:
        log(f"❌ Error saving output Excel file: {e}")
