"""
Adds seed grades to a specific variety.

Inputs:
Excel file with Variety ID, Seed Grade Name, and Description.
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

    # Configuration for URLs
    # variety_url is typically the primary "Base Api Url" or "Post Api Url" in the UI config
    variety_url = config.get("post_api_url", "https://cloud.cropin.in/services/farm/api/varieties")
    # seed_grade_url is the secondary URL
    seed_grade_url = config.get("secondary_api_url", "https://cloud.cropin.in/services/farm/api/seed-grades")

    delay_time = float(config.get("delay_time", 0.5))  # seconds, configurable via UI

    def fetch_seed_grade(token):
        url = seed_grade_url
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def create_seed_grade(token, name, description):
        url = seed_grade_url
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "name": name,
            "description": description
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

    def update_variety(token, variety_data):
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        # Note: Previous scripts suggested `requests.put(f"{variety_url}", ...)` might work if ID is in body or specific API behavior.
        # But commonly it is `requests.put(f"{variety_url}/{id}", ...)`
        # The user provided script used: `response = requests.put(f"{variety_url}", headers=headers, json=variety_data)`
        # I will respect that.
        response = requests.put(f"{variety_url}", headers=headers, json=variety_data)
        response.raise_for_status()
        return response.json()

    log("⏳ Reading input file...")
    try:
        # Default to Sheet1 as per user script request, but pandas defaults to first sheet usually.
        df = pd.read_excel(input_excel) 
    except Exception as e:
        log(f"❌ Failed to read Excel file: {e}")
        return

    df['Status'] = ''
    df['Response'] = ''

    headers = {"Authorization": f"Bearer {token}"}
    
    log("⏳ Fetching existing seed grades...")
    try:
        seed_grade = fetch_seed_grade(token)
        seed_grade_names = {seed['name'].lower(): seed for seed in seed_grade}
    except Exception as e:
        log(f"❌ Failed to fetch seed grades: {e}")
        return

    for i, row in df.iterrows():
        try:
            # Column mapping based on user script:
            # 0: Variety ID
            # 1: Seed Grade Name
            # 2: Description
            
            variety_id = int(row.iloc[0]) if pd.notna(row.iloc[0]) else None
            seed_grade_name = row.iloc[1]
            description = row.iloc[2] if pd.notna(row.iloc[2]) else None

            if pd.isna(variety_id) or pd.isna(seed_grade_name):
                df.at[i, 'Status'] = "Skipped: Missing Variety ID or Seed Grade Name"
                df.at[i, 'Response'] = "Variety ID or Seed Grade Name is empty"
                log(f"\n⏳ Skipping row {i+2} due to missing data.")
                continue

            log(f"\n⏳ Processing Variety ID: {variety_id}, Seed Grade: {seed_grade_name}")

            variety_response = requests.get(f"{variety_url}/{variety_id}", headers=headers)
            variety_response.raise_for_status()
            variety_data = variety_response.json()

            seed_grade_to_add = seed_grade_names.get(str(seed_grade_name).lower())

            if not seed_grade_to_add:
                log(f"⚠️ Seed Grade '{seed_grade_name}' does not exist. Creating...")
                seed_grade_to_add = create_seed_grade(token, seed_grade_name, description)
                seed_grade_names[str(seed_grade_name).lower()] = seed_grade_to_add
            else:
                log(f"✅ Seed Grade '{seed_grade_name}' already exists.")

            existing_stages = variety_data.get("seedGrades", [])
            if any(seed['name'].lower() == str(seed_grade_name).lower() for seed in existing_stages):
                log(f"⚠️ Seed Grade '{seed_grade_name}' already added to variety. Skipping update.")
                df.at[i, 'Status'] = "Skipped: Already Present"
                # Avoid dumping full JSON to excel cell
                df.at[i, 'Response'] = "Already Present" 
                continue

            variety_data.setdefault("seedGrades", []).append(seed_grade_to_add)
            
            update_variety(token, variety_data)
            
            log(f"✅ Updated variety with new seed grade: {seed_grade_name}")
            df.at[i, 'Status'] = "Success"
            df.at[i, 'Response'] = "Updated Successfully"

        except Exception as e:
            log(f"❌ Failed to process row {i+2}: {str(e)}")
            df.at[i, 'Status'] = "Failed"
            df.at[i, 'Response'] = str(e)

        time.sleep(delay_time)

    df.to_excel(output_excel, index=False)
    log(f"\n✅ Processing complete. Output saved to {output_excel}")
