"""
Adds crop application master data to the application.
Author: Rajasekhar Palleti

Inputs:
Excel file containing Master Name and Master Type.
"""
import pandas as pd
import requests
import time

def run(input_excel, output_excel, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    token = config.get("token")
    if not token:
        log("❌ No token provided in configuration.")
        return

    post_api_url = config.get("base_api_url", "https://cloud.cropin.in/services/farm/api/cropApplicationMaster")
    list_api_url = config.get("second_base_api_url", "https://cloud.cropin.in/services/master/api/cropApplicationMaster/list")
    
    delay_time = float(config.get("delay_time", 0.5))

    def get_existing_master_names(token, list_api_url, master_type):
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{list_api_url}?type={master_type}&size=5000", headers=headers)
        response.raise_for_status()
        data = response.json()
        existing_names = set()
        for item in data:
            if item.get("name"):
                existing_names.add(item["name"].strip().lower())
        log(f"Found {len(existing_names)} existing {master_type} records")
        return existing_names

    log("Reading Excel File...")
    df = pd.read_excel(input_excel)

    # Determine columns for Type and Name
    if "Type" in df.columns and "Name" in df.columns:
        type_col = "Type"
        name_col = "Name"
    elif len(df.columns) >= 2:
        type_col = df.columns[0]
        name_col = df.columns[1]
        log(f"Warning: 'Type' or 'Name' columns not found. Using column 1 ('{type_col}') as Type and column 2 ('{name_col}') as Name.")
    else:
        log("JOB_FAILED::Excel file must have at least 2 columns.")
        return

    if "Status" not in df.columns:
        df["Status"] = ""
    if "Response" not in df.columns:
        df["Response"] = ""

    df['Status'] = df['Status'].fillna("").astype(str)
    df['Response'] = df['Response'].fillna("").astype(str)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    default_valid_types = [
        "ACTIVE_INGREDIENT",
        "APPLICATION_TYPE",
        "BRAND_NAME",
        "MODE_OF_APPLICATION"
    ]

    # Get from the UI config payload (config dict passed to run)
    config_valid_types = config.get("valid_types")

    if config_valid_types:
        if isinstance(config_valid_types, str):
            VALID_TYPES = [t.strip().upper() for t in config_valid_types.split(",") if t.strip()]
        elif isinstance(config_valid_types, list):
            VALID_TYPES = [str(t).strip().upper() for t in config_valid_types]
        else:
            VALID_TYPES = default_valid_types
    else:
        VALID_TYPES = default_valid_types

    existing_data_cache = {}
    processed_excel_records = set()
    total_rows = len(df)

    for index, row in df.iterrows():
        try:
            master_type = str(row.get(type_col, "")).strip().upper()
            master_name = str(row.get(name_col, "")).strip()

            executed = index
            pending = total_rows - executed
            log(f"\n⏳ Processing Row {index + 1} | Executed: {executed} | Pending: {pending} | Total: {total_rows}")

            if pd.isna(row.get(name_col)) or master_name == "" or master_name.lower() == "nan":
                df.at[index, "Status"] = "Skipped"
                df.at[index, "Response"] = "Empty Name"
                continue            

            if master_type not in VALID_TYPES:
                df.at[index, "Status"] = "Skipped"
                df.at[index, "Response"] = f"Invalid Type : {master_type}"
                continue

            if master_type not in existing_data_cache:
                log(f"Fetching existing {master_type} records...")
                existing_data_cache[master_type] = get_existing_master_names(token, list_api_url, master_type)

            existing_names = existing_data_cache[master_type]
            unique_key = f"{master_type}|{master_name.lower()}"

            if master_name.lower() in existing_names:
                log(f"Skipping {master_name} - Already exists in API")
                df.at[index, "Status"] = "Skipped"
                df.at[index, "Response"] = "Already exists in API"
                continue

            if unique_key in processed_excel_records:
                log(f"Skipping {master_name} - Duplicate in Excel")
                df.at[index, "Status"] = "Skipped"
                df.at[index, "Response"] = "Duplicate in Excel"
                continue

            payload = {
                "type": master_type,
                "name": master_name,
                "id": None
            }

            log(f"Creating {master_type} : {master_name}")
            response = requests.post(post_api_url, headers=headers, json=payload)

            if response.status_code in [200, 201]:
                log(f"✅ Created successfully : {master_name}")
                df.at[index, "Status"] = "Success"
                df.at[index, "Response"] = response.text
                processed_excel_records.add(unique_key)
                existing_names.add(master_name.lower())
            else:
                df.at[index, "Status"] = f"Failed : {response.status_code}"
                df.at[index, "Response"] = f"Reason : {response.reason}, Message : {response.text}"

        except Exception as e:
            log(f"❌ Error processing row {index + 1}: {str(e)}")
            df.at[index, "Status"] = "Error"
            df.at[index, "Response"] = str(e)

        time.sleep(delay_time)

    log("\nSaving updated DataFrame to output Excel...")
    df.to_excel(output_excel, index=False)
    log(f"✅ Processing completed. Output saved to {output_excel}")
