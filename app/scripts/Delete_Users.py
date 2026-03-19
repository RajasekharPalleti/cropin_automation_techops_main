# Author: Rajasekhar Palleti
# Purpose: Disable users in bulk (50 IDs per request)

"""
This script disables users in bulk by calling the delete API in batches of 50.
Inputs:
Excel file with a 'user_id' column.
"""

import pandas as pd
import requests
import time

# =========================
# CONFIGURATION
# =========================
DEFAULT_API_URL = "https://cloud.cropin.in/services/user/api/users/bulk"
BATCH_SIZE = 50
DELAY_SECONDS = 5 # Delay between batches to avoid rate limiting

def run(input_excel, output_excel, config, log_callback=None):
    """
    Executes the Delete Users process.
    """
    def log(message):
        if log_callback:
            log_callback(message)
        print(message)

    token = config.get("token")
    if not token:
        log("❌ Error: Authorization token missing in configuration.")
        return

    # Determine API URL
    api_url = config.get("base_api_url")
    if not api_url:
        api_url = DEFAULT_API_URL
        log("ℹ️ Using default API URL.")
    else:
        log(f"ℹ️ Using configured API URL: {api_url}")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    delay_time = float(config.get("delay_time", 5))

    log(f"Reading input file: {input_excel}")
    try:
        df = pd.read_excel(input_excel)
    except Exception as e:
         log(f"❌ Failed to read Excel file: {e}")
         return

    if "user_id" not in df.columns:
        log("❌ Excel must contain 'user_id' column")
        return

    # Clean IDs
    try:
        df["user_id"] = df["user_id"].dropna().astype(int).astype(str)
    except Exception as e:
        log(f"❌ Error converting user_id to integer/string: {e}")
        return

    # Add result columns and ensure string type to avoid TypeError/nan strings
    for col in ["Status", "Processed_User_Ids", "API_Response"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    total_rows = len(df)
    processed_count = 0
    log(f"Total rows to process: {total_rows}")

    for i in range(0, total, BATCH_SIZE):
        batch_df = df.iloc[i:i + BATCH_SIZE]
        user_ids = batch_df["user_id"].tolist()
        
        if not user_ids:
            continue

        ids_param = ",".join(user_ids)
        batch_num = (i // BATCH_SIZE) + 1
        pending_rows = total_rows - processed_count

        log(f"🔁 Processing Batch {batch_num} (Rows {i+2} to {min(i+BATCH_SIZE+1, total_rows+1)}) | Items: {len(user_ids)} | Processed: {processed_count} | Pending: {pending_rows}")
        # log(f"👥 User IDs count: {len(user_ids)}")

        try:
            response = requests.delete(
                f"{api_url}?ids={ids_param}&enabled=false",
                headers=headers,
                timeout=30
            )

            status = "Success" if response.status_code in (200, 204) else f"Failed ({response.status_code})"
            response_text = response.text
            
            if status == "Success":
                 log(f"✅ Batch {batch_num} Successful")
            else:
                 log(f"❌ Batch {batch_num} Failed: {response.status_code} - {response.text}")

        except Exception as e:
            status = "Error"
            response_text = str(e)
            log(f"❌ Batch {batch_num} Exception: {e}")

        # Write result only in first row of batch
        first_index = batch_df.index[0]
        df.at[first_index, "Status"] = status
        df.at[first_index, "Processed_User_Ids"] = ids_param
        df.at[first_index, "API_Response"] = response_text
        
        processed_count += len(user_ids)
        time.sleep(delay_time)

    log("Saving output file...")
    try:
        df.to_excel(output_excel, index=False)
        log("✅ Process completed successfully.")
    except Exception as e:
        log(f"❌ Failed to save output file: {e}")
