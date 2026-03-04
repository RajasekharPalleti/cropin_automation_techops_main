"""
Enable / Disable Users from Excel

Inputs:
This script reads an Excel file containing user IDs and an enable flag to enable or disable users via API.

Required Columns in Excel:
- user_id: The ID of the user to update.
- enableFlag: 'true' to enable, 'false' to disable.
"""

import pandas as pd
import requests
import time
import os

# The 'run' function is the entry point called by the main application
def run(input_excel_path, output_excel_path, config, log_callback=None):
    """
    Executes the user enable/disable logic.
    
    Args:
        input_excel_path (str): Path to the uploaded input Excel file.
        output_excel_path (str): Path where the output Excel should be saved.
        config (dict): Configuration dictionary containing 'token' and 'url'.
        log_callback (func): Optional callback function to log messages.
    """
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg, flush=True)

    api_base_url = config.get("base_api_url")
    
    if not api_base_url or pd.isna(api_base_url):
         api_base_url = "https://cloud.cropin.in/services/user/api/users"
         log(f"⚠️ API URL not provided. Using default: {api_base_url}")
    token = config.get("token")

    # Delay to avoid rate limiting
    delay_time = float(config.get("delay_time", 0.2))  # configurable via UI

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    log("📂 Reading Excel file...")
    # Load the workbook first to get sheet names, defaulting to first sheet if "Sheet1" not found? 
    # Or just let pandas handle it. The original script used sheet_name="Sheet1". 
    # We'll use default (first sheet) to be more robust, or "Sheet1".
    # Let's stick to default behavior (first sheet) which is usually what users expect if they just upload a file.
    try:
        df = pd.read_excel(input_excel_path)
    except Exception as e:
        log(f"❌ Error reading input file: {e}")
        return

    # Ensure status columns exist
    if "Status" not in df.columns:
        df["Status"] = ""
    if "Response" not in df.columns:
        df["Response"] = ""

    total_rows = len(df)
    log(f"Processing {total_rows} rows...")

    for index, row in df.iterrows():
        user_id = row.get("user_id")
        enable_flag = row.get("enableFlag")

        if pd.isna(user_id) or pd.isna(enable_flag):
            df.at[index, "Status"] = "⚠️ Skipped: Missing Data"
            continue

        # Normalize enableFlag (true/false)
        enable_flag_str = str(enable_flag).lower()
        if enable_flag_str not in ["true", "false"]:
            df.at[index, "Status"] = "❌ Invalid enableFlag"
            continue

        # Construct URL
        # Ensure user_id is int
        try:
             u_id = int(user_id)
        except:
             df.at[index, "Status"] = "❌ Invalid User ID"
             continue

        url = f"{api_base_url}/enable/{u_id}?enableFlag={enable_flag_str}"

        log(f"🔄 Processing row {index + 1}/{total_rows} | UserID: {u_id} | enableFlag: {enable_flag_str}")

        try:
            response = requests.put(url, headers=headers)

            if response.status_code in [200, 204]:
                df.at[index, "Status"] = "✅ Success"
                df.at[index, "Response"] = response.text if response.text else "Success"
                log(f"✅ User {u_id} updated successfully")
            else:
                df.at[index, "Status"] = f"❌ Failed: {response.status_code}"
                df.at[index, "Response"] = response.text
                log(f"❌ Failed for User {u_id}: {response.status_code} | {response.text}")

        except Exception as e:
            df.at[index, "Status"] = "❌ Error"
            df.at[index, "Response"] = str(e)
            log(f"❌ Exception for User {u_id}: {e}")

        time.sleep(delay_time)

    log("💾 Saving output Excel...")
    try:
        df.to_excel(output_excel_path, index=False)
        log(f"✅ File saved: {output_excel_path}")
    except Exception as e:
        log(f"❌ Error saving output file: {e}")
