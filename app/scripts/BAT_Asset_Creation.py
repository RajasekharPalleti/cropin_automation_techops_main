"""
Creates assets under the BAT system using a POST request with multipart form data.
Reads asset names, farmer IDs, and declared areas from an Excel sheet.
Supports multithreading via worker_count config.

Author: Rajasekhar Palleti

Inputs:
Excel file with 'Asset Name', 'Farmer ID', and 'Declared Area' columns.
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
        api_url = "https://cloud.cropin.in/services/farm/api/assets"
        log(f"Using default Asset API URL: {api_url}")
    api_url = api_url.rstrip('/')

    MAX_WORKERS = int(config.get("worker_count", 2))
    delay_time = float(config.get("delay_time", 1.0))
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

    # 3. Detect column names from Excel flexibly
    name_col = next((c for c in df.columns if c.lower().replace('_', '').replace(' ', '') in ['assetname', 'name']), None)
    if not name_col:
        name_col = next((c for c in df.columns if 'name' in c.lower()), None)
    if not name_col:
        log("❌ Could not identify 'Asset Name' column (expected 'Asset Name' or 'name')")
        return
    log(f"ℹ️ Found Asset Name column: '{name_col}'")

    owner_col = next((c for c in df.columns if c.lower().replace('_', '').replace(' ', '') in ['farmerid', 'ownerid', 'farmer_id', 'owner_id']), None)
    if not owner_col:
        owner_col = next((c for c in df.columns if 'farmer' in c.lower() or 'owner' in c.lower()), None)
    if not owner_col:
        log("❌ Could not identify 'Farmer ID' / 'Owner ID' column (expected 'Farmer ID' or 'ownerId')")
        return
    log(f"ℹ️ Found Farmer ID column: '{owner_col}'")

    area_col = next((c for c in df.columns if c.lower().replace('_', '').replace(' ', '') in ['declaredarea', 'declared_area', 'area']), None)
    if not area_col:
        area_col = next((c for c in df.columns if 'area' in c.lower() or 'count' in c.lower()), None)
    if not area_col:
        log("❌ Could not identify 'Declared Area' column (expected 'Declared Area' or 'declared_area')")
        return
    log(f"ℹ️ Found Declared Area column: '{area_col}'")

    # 4. Ensure output columns exist and are string-safe (Pandas Type Safety)
    for col in ["Status", "Response", "Asset ID"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    total_rows = len(df)
    processed_count = 0
    processed_lock = threading.Lock()

    # Count already-executed rows for resume support
    already_done = df[df['Status'].str.strip().str.lower() == 'success'].shape[0]
    log(f"📊 Total rows: {total_rows} | Already Executed: {already_done} | Pending: {total_rows - already_done}")
    log(f"🚀 Starting asset creation with {MAX_WORKERS} workers...")

    # 5. Split DataFrame into chunks (one per worker)
    chunk_size = (total_rows + MAX_WORKERS - 1) // MAX_WORKERS  # ceiling division
    chunks = [df.iloc[i:i + chunk_size].copy() for i in range(0, total_rows, chunk_size)]
    actual_workers = min(len(chunks), MAX_WORKERS)

    # -------------------------------------------------
    # Thread Function — processes one chunk sequentially
    # -------------------------------------------------
    def process_chunk(df_chunk, thread_id):
        nonlocal processed_count
        results = []  # List of (index, status, response, asset_id)

        headers = {
            "Authorization": f"Bearer {token}"
            # Do NOT set Content-Type manually. requests sets multipart boundary automatically.
        }

        for index, row in df_chunk.iterrows():
            # Skip already successfully executed rows (resume support)
            current_status = str(row.get('Status', '')).strip().lower()
            if current_status == 'success':
                with processed_lock:
                    processed_count += 1
                continue

            name_val = str(row.get(name_col, "")).strip()
            owner_val = str(row.get(owner_col, "")).strip()
            area_val = row.get(area_col)

            # Row logging
            log(f"[Thread {thread_id}] 🔄 Row {index+2}: Processing asset '{name_val}' for Farmer '{owner_val}'")

            if not name_val or name_val.lower() in ["nan", "none", ""]:
                log(f"[Thread {thread_id}] ⚠️ Row {index+2} skipped: Asset Name is empty.")
                results.append((index, "Skipped", "Empty Asset Name", "N/A"))
                with processed_lock:
                    processed_count += 1
                    pending_rows = total_rows - processed_count
                    log(f"[Thread {thread_id}] Processed: {processed_count}/{total_rows} | Pending: {pending_rows}")
                continue

            if not owner_val or owner_val.lower() in ["nan", "none", ""]:
                log(f"[Thread {thread_id}] ⚠️ Row {index+2} skipped: Farmer ID is empty.")
                results.append((index, "Skipped", "Empty Farmer ID", "N/A"))
                with processed_lock:
                    processed_count += 1
                    pending_rows = total_rows - processed_count
                    log(f"[Thread {thread_id}] Processed: {processed_count}/{total_rows} | Pending: {pending_rows}")
                continue

            if pd.isna(area_val) or str(area_val).strip() == '':
                log(f"[Thread {thread_id}] ⚠️ Row {index+2} skipped: Declared Area is empty.")
                results.append((index, "Skipped", "Empty Declared Area", "N/A"))
                with processed_lock:
                    processed_count += 1
                    pending_rows = total_rows - processed_count
                    log(f"[Thread {thread_id}] Processed: {processed_count}/{total_rows} | Pending: {pending_rows}")
                continue

            try:
                declared_area_count = float(area_val)
            except ValueError:
                log(f"[Thread {thread_id}] ⚠️ Row {index+2} skipped: Invalid Declared Area value '{area_val}'")
                results.append((index, "Skipped", f"Invalid Declared Area: {area_val}", "N/A"))
                with processed_lock:
                    processed_count += 1
                    pending_rows = total_rows - processed_count
                    log(f"[Thread {thread_id}] Processed: {processed_count}/{total_rows} | Pending: {pending_rows}")
                continue

            # Build Payload
            asset_payload = {
                "data": {},
                "images": {},
                "companyStatus": "ACTIVE",
                "declaredArea": {
                    "enableConversion": "true",
                    "unit": "HECTARE",
                    "count": declared_area_count,
                    "name": name_val,
                    "ownerId": owner_val,
                    "address": {
                        "country": "Brazil",
                        "formattedAddress": "Brazil",
                        "administrativeAreaLevel1": "",
                        "locality": "",
                        "postalCode": "",
                        "houseNo": "",
                        "buildingName": "",
                        "placeId": "ChIJzyjM68dZnAARYz4p8gYVWik",
                        "latitude": -14.235004,
                        "longitude": -51.92528
                    }
                }
            }

            multipart_data = {"dto": (None, json.dumps(asset_payload), "application/json")}

            try:
                resp = requests.post(api_url, headers=headers, files=multipart_data)

                if resp.status_code in [200, 201]:
                    asset_id = "N/A"
                    try:
                        resp_json = resp.json()
                        if isinstance(resp_json, dict):
                            asset_id = resp_json.get("id") or resp_json.get("assetId") or "N/A"
                        elif isinstance(resp_json, list) and len(resp_json) > 0:
                            asset_id = resp_json[0].get("id") or resp_json[0].get("assetId") or "N/A"
                    except Exception:
                        pass
                    log(f"[Thread {thread_id}] ✅ Success: '{name_val}' | Asset ID: {asset_id}")
                    results.append((index, "Success", resp.text[:500], str(asset_id)))
                else:
                    log(f"[Thread {thread_id}] ❌ Failed: Row {index+2} - HTTP {resp.status_code}: {resp.text[:300]}")
                    results.append((index, f"Failed: {resp.status_code}", resp.text, "N/A"))

            except Exception as e:
                log(f"[Thread {thread_id}] ❌ Error: Row {index+2} - {e}")
                results.append((index, "Error", str(e), "N/A"))

            with processed_lock:
                processed_count += 1
                pending_rows = total_rows - processed_count
                log(f"[Thread {thread_id}] Processed: {processed_count}/{total_rows} | Pending: {pending_rows} | Asset: {name_val}")

            time.sleep(delay_time)

        return results

    # -------------------------------------------------
    # Execute Threads
    # -------------------------------------------------
    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        futures = [
            executor.submit(process_chunk, chunk, thread_id + 1)
            for thread_id, chunk in enumerate(chunks)
        ]
        chunk_results = []
        for future in futures:
            chunk_results.extend(future.result())

    # Update Main DataFrame
    log("💾 Aggregating results...")
    for idx, status, response, asset_id in chunk_results:
        if idx in df.index:
            df.at[idx, "Status"] = status
            df.at[idx, "Response"] = str(response)
            df.at[idx, "Asset ID"] = str(asset_id)

    # Save once at the end
    try:
        df.to_excel(output_excel_file, index=False)
        log(f"\n🎯 Process completed. Processed: {processed_count} | Total: {total_rows}")
        log(f"📁 Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"❌ Error saving output file: {e}")
