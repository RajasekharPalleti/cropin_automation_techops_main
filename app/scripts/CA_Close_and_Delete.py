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

    base_url = config.get("base_api_url")
    if not base_url:
        base_url = "https://cloud.cropin.in/services/farm/api"
        log(f"Using default API URL: {base_url}")
    base_url = base_url.rstrip('/')

    ca_action = config.get("ca_action", "close and delete CA")
    log(f"🚀 CA Action Mode: {ca_action}")

    batch_size = int(config.get("batch_size", 50))
    delay_time = float(config.get("delay_time", 5))  # seconds, configurable via UI

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
    project_asset_col = lower_cols["project_asset_id"]
    ca_col = lower_cols["croppable_area_id"]

    # Ensure only relevant status columns based on action mode and cast to string
    if "close" in ca_action:
        for col in ["closed_api_http_status", "closed_api_status"]:
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].fillna("").astype(str)
    if "delete" in ca_action:
        for col in ["delete_api_http_status", "delete_api_status"]:
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].fillna("").astype(str)

    # Clean and Format Data
    df[project_col] = df[project_col].astype(str).str.strip().replace(r'\.0$', '', regex=True)
    df[project_asset_col] = df[project_asset_col].astype(str).str.strip().replace(r'\.0$', '', regex=True)
    df[ca_col] = df[ca_col].astype(str).str.strip().replace(r'\.0$', '', regex=True)

    # Filter out empty required IDs
    df = df[
        (df[ca_col].notna()) & (df[ca_col].str.strip() != "") & (df[ca_col].str.lower() != "nan") &
        (df[project_col].notna()) & (df[project_col].str.strip() != "") & (df[project_col].str.lower() != "nan") &
        (df[project_asset_col].notna()) & (df[project_asset_col].str.strip() != "") & (df[project_asset_col].str.lower() != "nan")
    ]
    df.reset_index(drop=True, inplace=True)

    if df.empty:
        log("⚠️ No valid data to process after cleaning.")
        return

    ca_x_api_key = config.get("ca_x_api_key", "SEF5qQ6RTDGFWUc36SNuCKGYW1tVuGgGrX1iApUs5DGOc7MS")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-api-key": ca_x_api_key
    }

    grouped = df.groupby(project_col)
    total_projects = len(grouped)
    log(f"🔄 Found {total_projects} projects to process.")

    for p_idx, (project_id, group) in enumerate(grouped, 1):
        project_asset_ids_all = group[project_asset_col].tolist()
        ca_ids_all = group[ca_col].tolist()
        indices_all = group.index.tolist()

        log(f"\n📁 Project {project_id} ({p_idx}/{total_projects}) | Total Items: {len(ca_ids_all)}")

        for offset, (project_asset_chunk, ca_chunk, idx_chunk) in enumerate(
                zip(chunk_list(project_asset_ids_all, batch_size),
                    chunk_list(ca_ids_all, batch_size),
                    chunk_list(indices_all, batch_size))):

            first_row_index = idx_chunk[0]
            ca_ids_param = ",".join(map(str, ca_chunk))
            project_asset_ids_param = ",".join(map(str, project_asset_chunk))

            log(f"  🔁 Batch {offset + 1} | Items: {len(ca_chunk)}")

            # Log each row being processed in this batch
            for row_idx, (ca_id, project_asset_id) in enumerate(zip(ca_chunk, project_asset_chunk)):
                excel_row = idx_chunk[row_idx] + 2  # +2: 1 for header, 1 for 0-based index
                log(f"    📌 Row {excel_row} | project_id: {project_id} | croppable_area_id: {ca_id} | project_asset_id: {project_asset_id}")

            # --- 1) CLOSE CA API ---
            if "close" in ca_action:
                log(f"    🔒 Closing {len(ca_chunk)} croppable areas...")
                close_url = f"{base_url}/croppable-areas/closed?reasonId=4&ids={ca_ids_param}"

                start_time_close = time.time()
                try:
                    resp_close = requests.get(close_url, headers=headers, timeout=600)
                    close_status_code = resp_close.status_code
                    
                    try:
                        close_json = resp_close.json()
                    except:
                        close_json = None

                    # Summary Extraction
                    ca_status_map = {}
                    def extract(obj):
                        if isinstance(obj, dict):
                            if "id" in obj and "status" in obj:
                                ca_status_map[str(obj["id"])] = str(obj["status"])
                            for v in obj.values():
                                extract(v)
                        elif isinstance(obj, list):
                            for x in obj:
                                extract(x)

                    if isinstance(close_json, (dict, list)):
                        extract(close_json)

                    log(f"    📤 Processed IDs ({len(ca_chunk)}): {', '.join(map(str, ca_chunk))}")
                    log(f"    📥 Response IDs  ({len(ca_status_map)}): {', '.join(ca_status_map.keys()) if ca_status_map else 'None'}")
                    _missed = set(map(str, ca_chunk)) - set(ca_status_map.keys())
                    log(f"    📝 IDs missed in response ({len(_missed)}): {', '.join(_missed) if _missed else 'None'}")
                    
                    for row_idx, chunk_idx in enumerate(idx_chunk):
                        current_ca_id = str(ca_chunk[row_idx])
                        df.at[chunk_idx, "closed_api_http_status"] = str(close_status_code)
                        
                        if current_ca_id in ca_status_map:
                            df.at[chunk_idx, "closed_api_status"] = ca_status_map[current_ca_id]
                        else:
                            if ca_status_map:
                                df.at[chunk_idx, "closed_api_status"] = "Not found in response"
                            else:
                                df.at[chunk_idx, "closed_api_status"] = json.dumps(close_json or resp_close.text, default=str)
                    
                    elapsed_close = time.time() - start_time_close
                    if close_status_code == 200:
                        log(f"    ✅ Close Success (HTTP {close_status_code}) in {elapsed_close:.2f}s")
                    else:
                        log(f"    ⚠️ Close Warning (HTTP {close_status_code}) in {elapsed_close:.2f}s")

                except Exception as e:
                    elapsed_close = time.time() - start_time_close
                    log(f"    ❌ Close Error: {str(e)} in {elapsed_close:.2f}s")
                    for chunk_idx in idx_chunk:
                        df.at[chunk_idx, "closed_api_http_status"] = "Error"
                        df.at[chunk_idx, "closed_api_status"] = str(e)


                time.sleep(delay_time)
                log(f"    ⏳ Waiting for {delay_time} seconds before next process...")

            # --- 2) DELETE CROPPABLE AREA API ---
            if "delete" in ca_action:
                ca_chunk_for_delete = []
                project_asset_chunk_for_delete = []
                idx_chunk_for_delete = []

                if "close" in ca_action:
                    for row_idx, chunk_idx in enumerate(idx_chunk):
                        status = str(df.at[chunk_idx, "closed_api_status"]).strip().lower()
                        if status == "closed":
                            ca_chunk_for_delete.append(ca_chunk[row_idx])
                            project_asset_chunk_for_delete.append(project_asset_chunk[row_idx])
                            idx_chunk_for_delete.append(chunk_idx)
                        else:
                            df.at[chunk_idx, "delete_api_http_status"] = "Skipped"
                            df.at[chunk_idx, "delete_api_status"] = "Skipped (Not closed)"
                else:
                    ca_chunk_for_delete = ca_chunk
                    project_asset_chunk_for_delete = project_asset_chunk
                    idx_chunk_for_delete = idx_chunk

                if not ca_chunk_for_delete:
                    if "close" in ca_action:
                        log(f"    ⚠️ No croppable areas were successfully closed in this batch. Skipping delete.")
                else:
                    ca_ids_param_delete = ",".join(map(str, ca_chunk_for_delete))
                    project_asset_ids_param_delete = ",".join(map(str, project_asset_chunk_for_delete))

                    log(f"    🗑️ Deleting {len(ca_chunk_for_delete)} croppable_areas...")
                    # Construct URL explicitly to avoid requests URL-encoding commas (%2C)
                    delete_url = f"{base_url}/projects/{project_id}/project-assets/selected-ids?ids={project_asset_ids_param_delete}&croppableAreaIds={ca_ids_param_delete}"

                    start_time_delete = time.time()
                    try:
                        resp_delete = requests.delete(delete_url, headers=headers, timeout=600)
                        delete_status_code = resp_delete.status_code

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

                        for chunk_idx in idx_chunk_for_delete:
                            df.at[chunk_idx, "delete_api_http_status"] = str(delete_status_code)
                            df.at[chunk_idx, "delete_api_status"] = json.dumps(delete_info, default=str)

                        elapsed_delete = time.time() - start_time_delete
                        if is_deleted:
                            log(f"    ✅ Delete Success (Deletable: {deletable}, Non-Deletable: {non_deletable}) in {elapsed_delete:.2f}s")
                        else:
                            error_detail = json.dumps(delete_json) if delete_json is not None else resp_delete.text
                            log(f"    ❌ Delete Failed (HTTP {delete_status_code}) in {elapsed_delete:.2f}s | Response: {error_detail[:500]}")

                    except Exception as e:
                        elapsed_delete = time.time() - start_time_delete
                        log(f"    ❌ Delete Error: {str(e)} in {elapsed_delete:.2f}s")
                        for chunk_idx in idx_chunk_for_delete:
                            df.at[chunk_idx, "delete_api_http_status"] = "Error"
                            df.at[chunk_idx, "delete_api_status"] = str(e)


                    time.sleep(delay_time)
                    log(f"    ⏳ Waiting for {delay_time} seconds before next process...")

            # Live save to output
            try:
                df.to_excel(output_excel_file, index=False)
            except:
                pass

    log(f"\n🎯 Process completed. Output saved to: {output_excel_file}")
