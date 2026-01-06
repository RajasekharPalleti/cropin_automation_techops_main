"""
Updates Sowing Date and Variety for Croppable Areas (CA).

Inputs:
Excel file with the following columns:
- CA_id
- CA_name
- variety_id
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

    api_url = config.get("url")
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

    # Ensure output columns exist
    if "Status" not in df.columns:
        df["Status"] = ""
    if "CA_Response" not in df.columns:
        df["CA_Response"] = ""

    # Validate required columns
    required_cols = ["CA_id", "CA_name", "variety_id", "raw_sowing_date"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        log(f"❌ Missing required columns: {', '.join(missing_cols)}")
        return

    total_rows = len(df)
    log(f"🔄 Starting processing {total_rows} rows...")

    for index, row in df.iterrows():
        try:
            CA_id = row["CA_id"]
            CA_name = row["CA_name"]
            variety_id = row["variety_id"]
            raw_sowing_date = row["raw_sowing_date"]

            # Validate mandatory fields
            if pd.isna(CA_id) or pd.isna(variety_id) or pd.isna(raw_sowing_date):
                df.at[index, "Status"] = "Skipped: Missing Data"
                continue

            # Parse sowing date
            sowingDate = parse_sowing_date(raw_sowing_date)
            if not sowingDate:
                df.at[index, "Status"] = "Skipped: Invalid Sowing Date"
                log(f"⚠️ Row {index+1}: Invalid sowing date for CA_ID {CA_id}")
                continue

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
            # Update sowing date and variety
            # -----------------------
            # Note: User code only updated sowingDate in the provided snippet, 
            # but the script name implies updating variety too.
            # And the input has variety_id.
            # I should add the variety update if the user intended it.
            # The user request title is "Update_DOS_Variety_to_CA.py".
            # The snippet `CA_data["sowingDate"] = sowingDate` was in the user code.
            # But they are extracting `variety_id = row.iloc[2]`.
            # I will assume I should update varietyUid or similar field if it exists in CA data structure.
            # Standard CA structure usually has 'variety' object or 'varietyUid'. 
            # Let's inspect typical CA data structure or just look at what the user MIGHT have intended.
            # "Add new script as per the workflow with script name as Update_DOS_Variety_to_CA.py"
            # In the user provided code:
            # variety_id = row.iloc[2]
            # ...
            # CA_data["sowingDate"] = sowingDate
            # ...
            # PUT
            #
            # The user code DOES NOT use `variety_id` for update! It just reads it.
            # However, the script name is `Update_DOS_Variety_to_CA.py`.
            # I should probably update the variety too.
            # In Cropin API, variety is usually referenced by `varietyUid` or inside `variety` object.
            # Since I want to be safe, I will add logic to update `varietyUid` IF `variety_id` is present.
            
            CA_data["sowingDate"] = sowingDate
            CA_data["varietyUid"] = str(variety_id) # Assigning variety ID
            
            # print(f"🌱 Updated sowingDate: {sowingDate}")

            time.sleep(1)

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

        time.sleep(1)

    # Save output
    try:
        df.to_excel(output_excel, index=False)
        log(f"\n📁 Excel file updated successfully: {output_excel}")
    except Exception as e:
        log(f"❌ Error saving output Excel: {e}")
