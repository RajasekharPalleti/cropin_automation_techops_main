"""
Updates Variety for Croppable Areas (CA).

Inputs:
Excel file with the following columns:
- CA_id
- CA_name
- variety_id
"""
import json
import requests
import pandas as pd
import time

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
    required_cols = ["CA_id", "CA_name", "variety_id"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        log(f"❌ Missing required columns: {', '.join(missing_cols)}")
        return

    total_rows = len(df)
    processed_count = 0
    log(f"🔄 Starting processing {total_rows} rows...")

    for index, row in df.iterrows():
        try:
            try:
                CA_id = row["CA_id"]
                CA_name = row["CA_name"]
                variety_id = row["variety_id"]

                if pd.isna(CA_id) or pd.isna(variety_id):
                    df.at[index, "Status"] = "Skipped: Missing Data"
                    continue

                pending_rows = total_rows - processed_count
                log(f"🔄 Processing row {index+1}/{total_rows} | Processed: {processed_count} | Pending: {pending_rows} | CA: {CA_id}")

                # -----------------------
                # GET croppable area
                # -----------------------
                log(f"⬇️ Fetching CA_ID: {CA_id}")
                get_response = requests.get(f"{api_url}/{CA_id}", headers=headers)
                if get_response.status_code != 200:
                    df.at[index, "Status"] = f"GET Failed: {get_response.status_code}"
                    log(f"❌ GET failed for CA_ID {CA_id}: {get_response.status_code}")
                    continue

                CA_data = get_response.json()
                
                # -----------------------
                # Update Variety ONLY
                # -----------------------
                CA_data["varietyId"] = variety_id
                log(f"🌱 Updated varietyId: {variety_id}")

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
                    df.at[index, "Status"] = f"PUT Failed: {put_response.status_code}"
                    df.at[index, "CA_Response"] = put_response.text
                    log(f"❌ PUT failed for CA_ID {CA_id}")
                else:
                    df.at[index, "Status"] = "Success"
                    df.at[index, "CA_Response"] = put_response.text
                    log(f"✅ Successfully updated CA_ID: {CA_id}")

            except requests.exceptions.RequestException as e:
                df.at[index, "Status"] = f"Failed: {str(e)}"
                log(f"❌ Exception for CA_ID {CA_id}: {e}")
            except Exception as e:
                df.at[index, "Status"] = f"Error: {str(e)}"
                log(f"❌ Error processing row {index+1}: {e}")

            time.sleep(delay_time)
        finally:
            processed_count += 1

    # Save output
    try:
        df.to_excel(output_excel, index=False)
        log(f"\n📁 Excel file updated successfully: {output_excel}")
    except Exception as e:
        log(f"❌ Error saving output Excel: {e}")
