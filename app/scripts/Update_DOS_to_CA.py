"""
Updates Sowing Date for Croppable Areas (CA).

Inputs:
Excel file with the following columns:
- CA_id
- CA_name
- raw_sowing_date
"""
import json
import requests
import pandas as pd
import time

# -------------------------------------------------
# Robust sowing date parser (handles ALL formats)
# -------------------------------------------------
def parse_sowing_date(raw_date):
    """
    Supported formats:
    - Excel Timestamp
    - dd/MM/yyyy
    - dd-MM-yyyy
    - yyyy-MM-dd
    - yyyy-MM-ddTHH:mm:ss
    - yyyy-MM-dd HH:mm:ss
    """

    if pd.isna(raw_date):
        return None

    try:
        parsed_date = pd.to_datetime(
            raw_date,
            dayfirst=True,   # IMPORTANT for 06/10/1994
            errors="raise"
        )

        # Keep time if provided, else normalize to 00:00:00
        return parsed_date.strftime("%Y-%m-%dT%H:%M:%S.000+0000")

    except Exception as e:
        return None


# -------------------------------------------------
# Main processing function
# -------------------------------------------------
def run(input_excel, output_excel, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    token = config.get("token")
    if not token:
        log("❌ No token provided in configuration.")
        return

    args_delay = config.get("delay_time", 1) 
    try:
        delay_time = float(args_delay)
    except:
        delay_time = 1

    api_url = config.get("base_api_url")
    if not api_url:
        api_url = "https://cloud.cropin.in/services/farm/api/croppable-areas" # Default
        log(f"Using default CA API URL: {api_url}")
    
    api_url = api_url.rstrip('/')

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    log(f"📘 Loading Excel file: {input_excel}")
    try:
        df = pd.read_excel(input_excel)
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    # Ensure output columns exist and are explicitly cast to string to avoid TypeError
    if "Status" not in df.columns:
        df["Status"] = ""
    df["Status"] = df["Status"].fillna("").astype(str)
    
    if "CA_Response" not in df.columns:
        df["CA_Response"] = ""
    df["CA_Response"] = df["CA_Response"].fillna("").astype(str)

    # Validate required columns
    required_cols = ["CA_id", "CA_name", "raw_sowing_date"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        log(f"❌ Missing required columns: {', '.join(missing_cols)}")
        return

    total_rows = len(df)
    processed_count = 0
    log(f"🔄 Starting processing {total_rows} rows...")

    import concurrent.futures
    import threading

    # Thread-safe logging
    log_lock = threading.Lock()
    processed_lock = threading.Lock()
    def thread_safe_log(msg):
        with log_lock:
            log(msg)

    def process_row(index, row):
        nonlocal processed_count
        try:
            CA_id = row["CA_id"]
            CA_name = row["CA_name"]
            raw_sowing_date = row["raw_sowing_date"]

            # Validate mandatory fields
            if pd.isna(CA_id) or pd.isna(raw_sowing_date):
                return index, "Skipped: Missing Data", "", None

            # Parse sowing date
            sowingDate = parse_sowing_date(raw_sowing_date)
            if not sowingDate:
                thread_safe_log(f"⚠️ Row {index+1}: Invalid sowing date for CA_ID {CA_id}")
                return index, "Skipped: Invalid Sowing Date", "", None

            # -----------------------
            # GET croppable area
            # -----------------------
            thread_safe_log(f"🔄 Processing row {index+1}/{total_rows}: Fetching CA_ID {CA_id}")
            get_response = requests.get(f"{api_url}/{CA_id}", headers=headers)
            if get_response.status_code != 200:
                thread_safe_log(f"❌ GET failed for CA_ID {CA_id}: {get_response.status_code}")
                return index, f"GET Failed: {get_response.status_code}", "", None

            CA_data = get_response.json()
            
            # -----------------------
            # Update sowing date ONLY
            # -----------------------
            CA_data["sowingDate"] = sowingDate
            # thread_safe_log(f"🌱 Updated sowingDate for {CA_id}: {sowingDate}")

            time.sleep(delay_time)

            # -----------------------
            # PUT update CA
            # -----------------------
            put_response = requests.put(
                api_url,
                headers=headers,
                data=json.dumps(CA_data)
            )

            if put_response.status_code != 200:
                thread_safe_log(f"❌ PUT failed for CA_ID {CA_id}")
                return index, f"PUT Failed: {put_response.status_code}", put_response.text, None
            else:
                thread_safe_log(f"✅ Successfully updated CA_ID: {CA_id}")
                return index, "Success", put_response.text, None

        except requests.exceptions.RequestException as e:
            thread_safe_log(f"❌ Exception for CA_ID {CA_id}: {e}")
            result_tuple = (index, f"Failed: {str(e)}", "", None)
        except Exception as e:
            thread_safe_log(f"❌ Error processing row {index+1}: {e}")
            result_tuple = (index, f"Error: {str(e)}", "", None)
        finally:
            with processed_lock:
                processed_count += 1
                pending_rows = total_rows - processed_count
                thread_safe_log(f"🔄 Processed: {processed_count}/{total_rows} | Pending: {pending_rows} | CA: {CA_id}")
        
        return result_tuple

    # Use ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(process_row, index, row): index for index, row in df.iterrows()}
        
        for future in concurrent.futures.as_completed(futures):
            processed_index, status, response, _ = future.result()
            df.at[processed_index, "Status"] = status
            df.at[processed_index, "CA_Response"] = response
            



    # Save output
    try:
        df.to_excel(output_excel, index=False)
        log(f"\n📁 Excel file updated successfully: {output_excel}")
    except Exception as e:
        log(f"❌ Error saving output Excel: {e}")
