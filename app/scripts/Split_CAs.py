"""
Splits croppable areas into multiple smaller areas based on split count.

Inputs:
Excel file with:
- croppable_area_id (Column 1)
- project_id (Column 2)
- total_area (Column 3)
- split_count (Column 4)
"""
import pandas as pd
import requests
import time
import json

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    # =========================
    # ACCESS TOKEN
    # =========================
    token = config.get("token")
    if not token:
        log("❌ Token missing. Exiting.")
        return
    log("✅ Access token loaded")

    # =========================
    # API CONFIG
    # =========================
    # Default to projects base URL
    default_url = "https://cloud.cropin.in/services/farm/api/projects"
    base_api_url = config.get("post_api_url")
    if not base_api_url:
        base_api_url = default_url
        log(f"Using default URL: {base_api_url}")
    else:
        log(f"Using configured URL: {base_api_url}")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    delay_time = float(config.get("delay_time", 2))  # seconds, configurable via UI

    # =========================
    # LOAD EXCEL
    # =========================
    log(f"📘 Loading Excel file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    # Add result columns
    if "status" not in df.columns:
        df["status"] = ""
    if "Response" not in df.columns:
        df["Response"] = ""

    # =========================
    # PROCESS ROWS
    # =========================
    for i in range(len(df)):
        try:
            # Using iloc as per user's original script requirement
            # Column 1 -> Index 0: croppable_area_id
            # Column 2 -> Index 1: project_id
            # Column 4 -> Index 3: total_area
            # Column 5 -> Index 4: split_count (User said Col 6, but code used index 4. Using index 4 as per code logic).
            
            croppable_area_id = df.iloc[i, 0]
            project_id = df.iloc[i, 1]
            # Skip empty rows
            if pd.isna(croppable_area_id) or pd.isna(project_id):
                continue

            croppable_area_id = int(croppable_area_id)
            project_id = int(project_id)
            
            try:
                # Updated mapping as per user request (0, 1, 2, 3)
                # Column 0: croppable_area_id
                # Column 1: project_id
                # Column 2: total_area
                # Column 3: split_count
                
                total_area = float(df.iloc[i, 2])
                split_count = int(df.iloc[i, 3])
            except (ValueError, IndexError):
                log(f"Skipping row {i+2} → Invalid area or split count")
                df.at[i, "status"] = "Skipped"
                df.at[i, "Response"] = "Invalid area or split count"
                continue

            if split_count < 1 or split_count > 50:
                log(f"Skipping row {i+2} → split_count {split_count} is 0 or invalid (must be 1-50)")
                df.at[i, "status"] = "Skipped"
                df.at[i, "Response"] = "Invalid split count"
                continue

            # Build URL: .../projects/{project_id}/croppable-areas/{croppable_area_id}/split
            # Ensure base_url doesn't have trailing slash for clean join, though f-string handles it.
            # Assuming base_api_url ends with /projects or is just the base. 
            # If user configured "https://.../projects", we use it as prefix.
            
            # Construct specific URL
            # The config url is passed as base. If it's the "projects" endpoint:
            # We need to construct: {base_api_url}/{project_id}/croppable-areas/{croppable_area_id}/split
            
            # Handle potential double slashes
            base_url_clean = base_api_url.rstrip("/")
            url = f"{base_url_clean}/{project_id}/croppable-areas/{croppable_area_id}/split"

            # Calculate split area & percentage
            split_area = round(total_area / split_count, 2)
            split_percentage = round(100 / split_count, 2)

            # Build payload
            payload = [
                {
                    "entities": [],
                    "splitArea": split_area,
                    "data": None,
                    "areaAuditDto": None,
                    "splitPercentage": split_percentage,
                    "name": None
                }
                for _ in range(split_count)
            ]

            log(f"➡ Processing Row {i+2} | Project {project_id}, CA {croppable_area_id}, Splits {split_count}")
            
            # API call
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                log(f"✅ Successfully split CA {croppable_area_id}")
                df.at[i, "status"] = "✅ Success"
                df.at[i, "Response"] = "Success"
            else:
                log(f"❌ Failed to split CA {croppable_area_id}, Status: {response.status_code}")
                df.at[i, "status"] = "❌ Failed"
                df.at[i, "Response"] = f"{response.status_code} - {response.text}"
                
            time.sleep(delay_time)  # configurable via UI

        except Exception as e:
            log(f"❌ Error processing row {i+2}: {e}")
            df.at[i, "status"] = "❌ Error"
            df.at[i, "Response"] = str(e)

    # =========================
    # SAVE EXCEL
    # =========================
    log("💾 Writing results to Excel...")
    try:
        df.to_excel(output_excel_file, index=False)
        log(f"🎯 Done. Excel updated successfully at: {output_excel_file}")
    except Exception as e:
        log(f"❌ Error saving output: {e}")
