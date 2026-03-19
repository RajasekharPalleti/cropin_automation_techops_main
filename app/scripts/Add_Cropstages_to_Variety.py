"""
Adds crop stages to a specific variety.

Inputs:
Excel file with Variety ID, Crop Stage Name, Description, and Days After Sowing.
"""
import json
import requests
import pandas as pd
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

    # Use URLs from config if provided, otherwise default to the ones in the prompt (or make them configurable)
    # The user prompt had specific URLs.
    cropstage_url = config.get("second_base_api_url", "https://cloud.cropin.in/services/farm/api/crop-stages")
    variety_url = config.get("base_api_url", "https://cloud.cropin.in/services/farm/api/varieties")

    delay_time = float(config.get("delay_time", 0.5))  # seconds, configurable via UI

    # Allow overriding via config if we want to be fancy, but user snippet was specific.
    # config['url'] from main.py usually maps to one of them.
    # Let's stick to the logic of the user script which uses these hardcoded global vars
    # but adapted to the `run` method scope.

    def fetch_crop_stages(token):
        url = cropstage_url
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def create_crop_stage(token, name, description, days_after_sowing):
        url = cropstage_url
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "name": name,
            "description": description,
            "daysAfterSowing": days_after_sowing
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

    def update_variety(token, variety_id, variety_data):
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # NOTE: Just in case, I will try to be robust. 
        # But let's check if variety_data has 'id'.
        # For now, copying user logic.
        
        response = requests.put(f"{variety_url}", headers=headers, json=variety_data)
        response.raise_for_status()
        return response.json()

    df = pd.read_excel(input_excel)
    df['Status'] = ''
    df['Response'] = ''
    # Explicitly cast to string after filling NaNs to prevent TypeError in newer pandas versions
    df['Status'] = df['Status'].fillna("").astype(str)
    df['Response'] = df['Response'].fillna("").astype(str)

    total_rows = len(df)
    processed_count = 0

    headers = {"Authorization": f"Bearer {token}"}
    
    log("⏳ Fetching crop stages...")
    try:
        crop_stages = fetch_crop_stages(token)
        crop_stage_names = {stage['name'].lower(): stage for stage in crop_stages}
    except Exception as e:
        log(f"❌ Failed to fetch crop stages: {e}")
        return

    for i, row in df.iterrows():
        try:
            # Indices: 0=VarietyID, 1=CropStageName, 2=Description, 3=DaysAfterSowing
            # Be careful with indices if user changes columns. 
            # Prompt says: "required fileds., called varietyID, Cropstagename, description and daysaftersowing."
            # So I assume columns 0, 1, 2, 3.
            
            variety_id = int(row.iloc[0]) if pd.notna(row.iloc[0]) else None
            crop_stage_name = row.iloc[1]
            description = row.iloc[2] if pd.notna(row.iloc[2]) else None
            days_after_sowing = row.iloc[3] if pd.notna(row.iloc[3]) else None

            if pd.isna(variety_id) or pd.isna(crop_stage_name):
                df.at[i, 'Status'] = "Skipped: Missing Variety ID or Crop Stage Name"
                df.at[i, 'Response'] = "Variety ID or Crop Stage Name is empty"
                log(f"\n⏳ Skipping row {i+2} due to missing data.")
                continue

            pending_rows = total_rows - processed_count
            log(f"\n⏳ Processing Variety ID: {variety_id}, Crop Stage: {crop_stage_name} (Row {i+2}/{total_rows+1}) | Processed: {processed_count} | Pending: {pending_rows}")

            variety_response = requests.get(f"{variety_url}/{variety_id}", headers=headers)
            variety_response.raise_for_status()
            variety_data = variety_response.json()

            crop_stage_template = crop_stage_names.get(str(crop_stage_name).lower())

            if not crop_stage_template:
                # create stage if missing in master
                log(f"⚠️ Crop stage '{crop_stage_name}' does not exist. Creating...")
                crop_stage_template = create_crop_stage(token, crop_stage_name, description, days_after_sowing)
                crop_stage_names[str(crop_stage_name).lower()] = crop_stage_template
            else:
                log(f"✅ Crop stage '{crop_stage_name}' found in master.")

            # Check if stage already present in variety
            existing_stages = variety_data.get("cropStages", [])
            if any(stage['name'].lower() == str(crop_stage_name).lower() for stage in existing_stages):
                log(f"⚠️ Crop stage '{crop_stage_name}' already added to variety. Skipping update.")
                df.at[i, 'Status'] = "Skipped: Already Present"
                df.at[i, 'Response'] = "Already Present" # Reduced JSON dump to avoid clutter in excel cell
                continue

            # Work on a copy to avoid mutating the master directly
            stage_to_add = crop_stage_template.copy()

            # If daysAfterSowing is missing/null/empty in the stage object, set it from Excel (if Excel provided it)
            if pd.notna(days_after_sowing) and (
                    stage_to_add.get('daysAfterSowing') is None or stage_to_add.get('daysAfterSowing') == ''):
                # convert to int if possible, otherwise keep as-is
                try:
                    stage_value = int(days_after_sowing)
                except (ValueError, TypeError):
                    stage_value = days_after_sowing
                stage_to_add['daysAfterSowing'] = stage_value

            # append and update
            variety_data.setdefault("cropStages", []).append(stage_to_add)
            
            
            update_response = update_variety(token, variety_id, variety_data)
            log(f"✅ Updated variety with new crop stage: {crop_stage_name}")
            df.at[i, 'Response'] = "Updated Successfully"

            processed_count += 1
        except Exception as e:
            processed_count += 1
            log(f"❌ Failed to process row {i+2}: {str(e)}")
            df.at[i, 'Status'] = "Failed"
            df.at[i, 'Response'] = str(e)

        time.sleep(delay_time)

    df.to_excel(output_excel, index=False)
    log(f"\n✅ Processing complete. Output saved to {output_excel}")
