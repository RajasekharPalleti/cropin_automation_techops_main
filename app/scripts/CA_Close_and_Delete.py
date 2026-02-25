"""
Close and/or Delete Croppable Areas (CA) dynamically based on dropdown selection.

Author: Rajasekhar Palleti

Inputs:
Excel file with:
- project_id
- croppable_area_id
- project_asset_id
"""

import pandas as pd
import requests
import json
import time

def chunk_list(lst, size):
    """Yield successive chunks from list `lst` of length `size`."""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    # Configuration
    token = config.get("token")
    if not token:
        log("❌ No token provided in configuration or invalid token.")
        return

    base_url = config.get("url")
    if not base_url:
        base_url = "https://cloud.cropin.in/services/farm/api"
        log(f"Using default API URL: {base_url}")
    base_url = base_url.rstrip('/')

    ca_action = config.get("ca_action", "close and delete CA")
    log(f"🚀 CA Action Mode: {ca_action}")

    batch_size = 100
    delay_time = 5  # seconds

    log(f"📘 Loading Excel file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    expected = ["project_id", "project_asset_id", "croppable_area_id"]
    lower_cols = {c.lower().strip(): c for c in df.columns}

    for exp in expected:
        if exp not in lower_cols:
            log(f"❌ Missing required column: {exp}")
            return

    project_col = lower_cols["project_id"]
    asset_col = lower_cols["project_asset_id"]
    ca_col = lower_cols["croppable_area_id"]

    # Ensure only relevant status columns based on action mode
    if "close" in ca_action:
        for col in ["closed_api_http_status", "closed_api_status"]:
            if col not in df.columns:
                df[col] = ""
    if "delete" in ca_action:
        for col in ["delete_api_http_status", "delete_api_status"]:
            if col not in df.columns:
                df[col] = ""

    # Clean and Format Data
    df[project_col] = df[project_col].astype(str).str.strip().replace(r'\.0$', '', regex=True)
    df[asset_col] = df[asset_col].astype(str).str.strip().replace(r'\.0$', '', regex=True)
    df[ca_col] = df[ca_col].astype(str).str.strip().replace(r'\.0$', '', regex=True)

    # Filter out empty CA IDs
    df = df[df[ca_col].notna() & (df[ca_col] != "") & (df[ca_col] != "nan")]
    df.reset_index(drop=True, inplace=True)

    if df.empty:
        log("⚠️ No valid data to process after cleaning.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    grouped = df.groupby(project_col)
    total_projects = len(grouped)
    log(f"🔄 Found {total_projects} projects to process.")

    for p_idx, (project_id, group) in enumerate(grouped, 1):
        asset_ids_all = group[asset_col].tolist()
        ca_ids_all = group[ca_col].tolist()
        indices_all = group.index.tolist()

        log(f"\n📁 Project {project_id} ({p_idx}/{total_projects}) | Total Items: {len(ca_ids_all)}")

        for offset, (asset_chunk, ca_chunk, idx_chunk) in enumerate(
                zip(chunk_list(asset_ids_all, batch_size),
                    chunk_list(ca_ids_all, batch_size),
                    chunk_list(indices_all, batch_size))):

            first_row_index = idx_chunk[0]
            ca_ids_param = ",".join(map(str, ca_chunk))
            asset_ids_param = ",".join(map(str, asset_chunk))

            log(f"  🔁 Batch {offset + 1} | Items: {len(ca_chunk)}")

            # Log each row being processed in this batch
            for row_idx, (ca_id, asset_id) in enumerate(zip(ca_chunk, asset_chunk)):
                excel_row = idx_chunk[row_idx] + 2  # +2: 1 for header, 1 for 0-based index
                log(f"    📌 Row {excel_row} | project_id: {project_id} | croppable_area_id: {ca_id} | project_asset_id: {asset_id}")

            # --- 1) CLOSE CA API ---
            if "close" in ca_action:
                log(f"    🔒 Closing {len(ca_chunk)} croppable areas...")
                close_url = f"{base_url}/croppable-areas/closed"
                close_params = {"reasonId": 4, "ids": ca_ids_param}

                try:
                    resp_close = requests.get(close_url, headers=headers, params=close_params, timeout=60)
                    close_status_code = resp_close.status_code
                    
                    try:
                        close_json = resp_close.json()
                    except:
                        close_json = None

                    # Summary Extraction
                    id_status_list = []
                    if isinstance(close_json, dict):
                        def extract(obj):
                            if isinstance(obj, dict):
                                if "id" in obj and "status" in obj:
                                    id_status_list.append({"id": obj["id"], "status": obj["status"]})
                                for v in obj.values():
                                    extract(v)
                            elif isinstance(obj, list):
                                for x in obj:
                                    extract(x)
                        extract(close_json)
                    elif isinstance(close_json, list):
                        for it in close_json:
                            if isinstance(it, dict) and "id" in it and "status" in it:
                                id_status_list.append({"id": it["id"], "status": it["status"]})

                    closed_api_summary = id_status_list or close_json or resp_close.text
                    df.at[first_row_index, "closed_api_http_status"] = close_status_code
                    df.at[first_row_index, "closed_api_status"] = json.dumps(closed_api_summary, default=str)
                    
                    if close_status_code == 200:
                        log(f"    ✅ Close Success (HTTP {close_status_code})")
                    else:
                        log(f"    ⚠️ Close Warning (HTTP {close_status_code})")

                except Exception as e:
                    log(f"    ❌ Close Error: {str(e)}")
                    df.at[first_row_index, "closed_api_http_status"] = "Error"
                    df.at[first_row_index, "closed_api_status"] = str(e)

                time.sleep(delay_time)

            # --- 2) DELETE PROJECT-ASSETS API ---
            if "delete" in ca_action:
                log(f"    🗑️ Deleting {len(ca_chunk)} project-assets...")
                delete_url = f"{base_url}/projects/{project_id}/project-assets/selected-ids"
                delete_params = {"ids": asset_ids_param, "croppableAreaIds": ca_ids_param}

                try:
                    resp_delete = requests.delete(delete_url, headers=headers, params=delete_params, timeout=120)
                    delete_status_code = resp_delete.status_code
                    delete_text = resp_delete.text

                    try:
                        delete_json = resp_delete.json()
                    except:
                        delete_json = None

                    deletable = None
                    non_deletable = None
                    is_deleted = False

                    if delete_status_code in (200, 204) and isinstance(delete_json, dict):
                        deletable = delete_json.get("deletable")
                        non_deletable = delete_json.get("nonDeletable")
                        if deletable is not None and non_deletable is not None:
                            is_deleted = True

                    delete_info = {
                        "http_status": delete_status_code,
                        "deletable": deletable,
                        "nonDeletable": non_deletable,
                        "deleted": is_deleted
                    }

                    df.at[first_row_index, "delete_api_http_status"] = delete_status_code
                    df.at[first_row_index, "delete_api_status"] = json.dumps(delete_info, default=str)

                    if is_deleted:
                        log(f"    ✅ Delete Success (Deletable: {deletable}, Non-Deletable: {non_deletable})")
                    else:
                        log(f"    ❌ Delete Failed (HTTP {delete_status_code})")

                except Exception as e:
                    log(f"    ❌ Delete Error: {str(e)}")
                    df.at[first_row_index, "delete_api_http_status"] = "Error"
                    df.at[first_row_index, "delete_api_status"] = str(e)

                time.sleep(delay_time)

            # Live save to output
            try:
                df.to_excel(output_excel_file, index=False)
            except:
                pass

    log(f"\n🎯 Process completed. Output saved to: {output_excel_file}")
