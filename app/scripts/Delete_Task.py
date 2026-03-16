"""
Delete tasks via bulk API and verify deletion by fetching tasks for the given Croppable Area.

Batching Details:
Given an Excel sheet with 'Task_Id' and 'CA_Id' per row:
1. Groups all tasks by their associated CA_Id.
2. For each CA_Id group, deletes tasks in batches of maximum 50 Task IDs at a time.
3. Automatically maps the API completion status back to the exact rows where the task IDs were inputted.

Inputs:
Excel file with 'Task_Id' (a single task ID) and 'CA_Id' (the related Croppable Area ID) per row.
"""

import requests
import pandas as pd
import time

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    api_url_delete = config.get("base_api_url", "https://cloud.cropin.in/services/farm/api/tasks/bulk")
    api_url_verify = config.get("second_base_api_url", "https://cloud.cropin.in/services/farm/api/tasks/croppablearea")
    token = config.get("token")
    delay_time = float(config.get("delay_time", 1.0))

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

    # Ensure tracking columns
    for col in ["Status", "Remarks"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    # Identify Task_Id and CA_Id columns
    task_id_col = None
    for possible in ["Task_Id", "Task_Ids", "task_id"]:
        if possible in df.columns:
            task_id_col = possible
            break
    if not task_id_col:
        task_id_col = df.columns[0]
        log(f"Warning: Could not find 'Task_Id' header. Falling back to Column: {task_id_col}")

    ca_id_col = None
    for possible in ["CA_Id", "ca_id", "CA_ID"]:
        if possible in df.columns:
            ca_id_col = possible
            break
    if not ca_id_col:
        ca_id_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
        log(f"Warning: Could not find 'CA_Id' header. Falling back to Column: {ca_id_col}")

    total_rows = len(df)
    log(f"Scanning {total_rows} rows to group by CA_Id...")

    # Group by CA_Id using pandas
    ca_groups = {}
    skipped_count = 0

    for index, row in df.iterrows():
        task_id_raw = row[task_id_col]
        ca_id_raw = row[ca_id_col]

        if pd.isna(task_id_raw) or pd.isna(ca_id_raw):
            df.at[index, "Status"] = "Skipped"
            df.at[index, "Remarks"] = "Missing Task_Id or CA_Id"
            skipped_count += 1
            continue

        # Handle numeric values and convert to string properly
        task_id_str = str(int(float(task_id_raw))).strip()
        ca_id_str = str(int(float(ca_id_raw))).strip()
            
        if ca_id_str not in ca_groups:
            ca_groups[ca_id_str] = []
        ca_groups[ca_id_str].append((index, task_id_str))

    log(f"Found {len(ca_groups)} unique CA IDs. (Skipped {skipped_count} invalid rows)")

    # Execute by groups and batches
    for ca_id_str, items in ca_groups.items():
        batch_size = 50
        total_tasks = len(items)
        log(f"--- Processing CA_Id: {ca_id_str} ({total_tasks} tasks) ---")

        for i in range(0, total_tasks, batch_size):
            batch = items[i:i + batch_size]
            batch_indices = [item[0] for item in batch]
            batch_task_ids = [item[1] for item in batch]
            clean_task_ids_str = ",".join(batch_task_ids)
            batch_num = (i // batch_size) + 1
            total_batches = (total_tasks + batch_size - 1) // batch_size
            
            log(f"[CA: {ca_id_str}] Batch {batch_num}/{total_batches}: Deleting {len(batch)} tasks...")
            
            try:
                # 1. Delete Tasks Request
                delete_url = f"{api_url_delete}?ids={clean_task_ids_str}"
                del_resp = requests.delete(delete_url, headers=req_headers)
                del_resp.raise_for_status()
                
                try:
                    del_json = del_resp.json()
                    deletable = del_json.get("deletable", 0)
                    non_deletable = del_json.get("nonDeletable", 0)
                    log(f"[CA: {ca_id_str}] Batch {batch_num}: Delete call success (Deletable: {deletable}, Non-Deletable: {non_deletable})")
                except Exception:
                    log(f"[CA: {ca_id_str}] Batch {batch_num}: Delete API responded successfully.")
                
                # Wait for 1 sec
                time.sleep(1)
                
                # 2. Verify Deletion Status Request
                log(f"[CA: {ca_id_str}] Batch {batch_num}: Verifying deletion via Croppable Area API...")
                verify_url = f"{api_url_verify}/{ca_id_str}?sort=lastModifiedDate,desc"
                ver_resp = requests.get(verify_url, headers=req_headers)
                ver_resp.raise_for_status()
                
                task_dtos = ver_resp.json()
                
                # The API returns a direct JSON array of tasks: [{"id": 3832313, ...}, ...]
                if isinstance(task_dtos, list):
                    tasks_list = task_dtos
                else:
                    tasks_list = task_dtos.get("content", task_dtos.get("data", task_dtos.get("taskDTOList", [task_dtos])))
                    
                active_task_ids_in_ca = set(str(t.get("id", "")) for t in tasks_list if isinstance(t, dict) and "id" in t)
                
                not_deleted_count = 0
                for idx, tid in batch:
                    if tid in active_task_ids_in_ca:
                        df.at[idx, "Status"] = "Not Deleted"
                        df.at[idx, "Remarks"] = f"Task ID {tid} was not deleted from CA {ca_id_str}"
                        not_deleted_count += 1
                    else:
                        df.at[idx, "Status"] = "Deleted"
                        df.at[idx, "Remarks"] = "Task successfully deleted"
                
                if not_deleted_count > 0:
                    log(f"[CA: {ca_id_str}] Batch {batch_num}: Complete. {not_deleted_count} tasks were not deleted.")
                else:
                    log(f"[CA: {ca_id_str}] Batch {batch_num}: Complete. All tasks deleted successfully.")
                    
            except requests.exceptions.RequestException as e:
                err_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        err_msg += f" - {e.response.text}"
                    except:
                        pass
                for idx, tid in batch:
                    df.at[idx, "Status"] = "Failed"
                    df.at[idx, "Remarks"] = err_msg
                log(f"[CA: {ca_id_str}] Batch {batch_num}: Failed - {err_msg[:100]}")

            # Throttle delay
            time.sleep(delay_time)

    # Save Output
    try:
        df.to_excel(output_excel_file, index=False)
        log(f"✅ Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"❌ Error saving output: {e}")
