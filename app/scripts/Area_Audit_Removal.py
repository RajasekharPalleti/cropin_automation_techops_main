"""
Removes area audits for specified croppable areas.

Inputs:
Excel file with Croppable Area IDs (`ca_id`).
"""
import pandas as pd
import requests

import time

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    # 1. Config
    token = config.get("token")
    if not token:
        log("❌ No token provided in configuration.")
        return

    # Base URL from config
    # Users provided example: https://cloud.cropin.in/services/farm/api/croppable-areas/{ca_id}/area-audit
    # The config should ideally provide: https://cloud.cropin.in/services/farm/api/croppable-areas
    base_api_url = config.get("post_api_url")
    if not base_api_url:
        base_api_url = "https://cloud.cropin.in/services/farm/api/croppable-areas"
        log(f"Using default Base URL: {base_api_url}")
    
    base_api_url = base_api_url.rstrip('/')

    delay_time = float(config.get("delay_time", 1))  # seconds, configurable via UI

    log(f"📂 Loading input file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    # Ensure columns
    for col in ["Status", "Response"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Processing Loop
    # User requested: "iterations should not be static" -> process all rows
    log(f"🔄 Processing {len(df)} rows...")
    
    success_count = 0
    failure_count = 0

    for index, row in df.iterrows():
        ca_id = str(row.get("ca_id", "")).strip()

        if not ca_id or ca_id.lower() == 'nan':
            # Skip empty
            continue

        # Construct URL: base/{ca_id}/area-audit
        # Assuming base ends with 'croppable-areas' or user provides root. 
        # Safety check: if user provided full path up to area-audit, we might double up.
        # But standard pattern is base resource URL.
        
        # If config is exactly "https://cloud.cropin.in/services/farm/api/croppable-areas"
        url = f"{base_api_url}/{ca_id}/area-audit"
        
        log(f"Processing {ca_id}...")

        try:
            response = requests.delete(url, headers=headers)
            status_code = response.status_code

            if status_code == 200:
                df.at[index, "Status"] = "Success"
                df.at[index, "Response"] = "200 OK"
                success_count += 1
                log(f"✅ {ca_id}: Success")
            else:
                df.at[index, "Status"] = f"Failed: {status_code}"
                df.at[index, "Response"] = response.text
                failure_count += 1
                log(f"⚠️ {ca_id}: Failed ({status_code})")

        except Exception as e:
            log(f"❌ Error {ca_id}: {e}")
            df.at[index, "Status"] = "Error"
            df.at[index, "Response"] = str(e)
            failure_count += 1

        time.sleep(delay_time)  # Rate limit protection

    try:
        df.to_excel(output_excel_file, index=False)
        log(f"💾 Completed. Success: {success_count}, Failures: {failure_count}. Saved to {output_excel_file}")
    except Exception as e:
        log(f"Error saving output: {e}")
