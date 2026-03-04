# Author: Rajasekhar Palleti
# Script: Cropin Connect (AcreSquare) Enablement – Batch of 100 with UserRole validation

"""
This script enables Cropin Connect (AcreSquare) for farmers in batches of 100.
It validates that each batch belongs to the same User Role ID before processing.
Inputs:
Excel file with 'farmer_id' and 'userRoleId' columns.
"""

import pandas as pd
import requests
import time
import os

# =========================
# CONFIG
# =========================
API_URL = "https://cloud.cropin.in/services/farm/api/acresquare/farmers-enable"
BATCH_SIZE = 100
DELAY = 5  # seconds

def run(input_excel, output_excel, config, log_callback=None):
    """
    Executes the Cropin Connect enablement process.
    """
    def log(message):
        if log_callback:
            log_callback(message)
        print(message)

    token = config.get("token")
    if not token:
        log("❌ Error: Authorization token missing in configuration.")
        return

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

    # Ensure required columns
    required_cols = ["farmer_id", "userRoleId"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        log(f"❌ Missing required columns: {missing_cols}")
        return

    # Add output columns if not present
    for col in ["Status", "Response"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str)

    total_rows = len(df)
    log(f"Total rows to process: {total_rows}")

    for start in range(0, total_rows, BATCH_SIZE):
        batch_df = df.iloc[start:start + BATCH_SIZE]
        batch_index = batch_df.index

        # Clean data: drop NaN, convert to int
        try:
            farmer_ids = batch_df["farmer_id"].dropna().astype(int).tolist()
            role_ids = batch_df["userRoleId"].dropna().astype(int).unique().tolist()
        except Exception as e:
            log(f"❌ Error processing batch starting at row {start}: {e}")
            continue

        if not farmer_ids:
            continue

        # ---- Validation: Same User Role ID ----
        if len(role_ids) != 1:
            msg = f"❌ Multiple UserRoleIds found in batch starting row {start+2}: {role_ids}. Batch skipped."
            log(msg)
            df.loc[batch_index, "Status"] = "Skipped"
            df.loc[batch_index, "Response"] = msg
            continue

        user_role_id = role_ids[0]
        payload = farmer_ids

        # Determine API URL
        base_url = config.get("base_api_url")
        if not base_url:
            base_url = API_URL
            log("ℹ️ Using default API URL.")
        else:
            log(f"ℹ️ Using configured API URL: {base_url}")

        log(f"🚀 Processing batch rows {start + 2} to {start + 1 + len(batch_df)}")
        log(f"👥 Farmers count: {len(farmer_ids)} | UserRoleId: {user_role_id}")

        try:
            response = requests.post(
                f"{base_url}?userRoleId={user_role_id}",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code in [200, 201, 204]:
                df.loc[batch_index, "Status"] = "Success"
                df.loc[batch_index, "Response"] = response.text
                log("✅ Enablement successful")
            else:
                df.loc[batch_index, "Status"] = f"Failed ({response.status_code})"
                df.loc[batch_index, "Response"] = response.text
                log(f"❌ API Failed: {response.status_code} - {response.text}")

        except Exception as e:
            df.loc[batch_index, "Status"] = "Error"
            df.loc[batch_index, "Response"] = str(e)
            log(f"❌ Exception: {e}")

        time.sleep(delay_time)

    log("Saving output file...")
    try:
        df.to_excel(output_excel, index=False)
        log("✅ Process completed successfully.")
    except Exception as e:
        log(f"❌ Failed to save output file: {e}")
