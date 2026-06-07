"""
Creates farmers for BAT system using a POST request with multipart form data.
Reads farmer names from an Excel sheet, creates them, and writes back the generated Farmer ID,
Status, and the raw Response. Supports multithreading via worker_count config.

Author: Rajasekhar Palleti

Inputs:
Excel file with 'Farmer Name' (or first column) to create farmers.
"""
import pandas as pd
import requests
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    # ================= CONFIG ================= #
    token = config.get("token")
    if not token:
        log("❌ No token provided in configuration.")
        return

    api_url = config.get("base_api_url")
    if not api_url:
        api_url = "https://cloud.cropin.in/services/farm/api/farmers"
        log(f"Using default Farmer API URL: {api_url}")
    api_url = api_url.rstrip('/')

    MAX_WORKERS = int(config.get("worker_count", 2))
    delay_time = float(config.get("delay_time", 1.0))
    # ========================================== #

    headers = {
        "Authorization": f"Bearer {token}"
        # ❌ Do NOT set Content-Type manually. requests sets the multipart boundary automatically.
    }

    # 2. Load Excel File
    log(f"📂 Loading input Excel file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
        # Remove unnamed columns
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    # 3. Detect Farmer Name column
    name_col = None
    possible_cols = ['farmer_name', 'Farmer Name', 'firstName', 'Name', 'name']
    for col in df.columns:
        if col in possible_cols:
            name_col = col
            break
    if not name_col:
        if len(df.columns) > 0:
            name_col = df.columns[0]
            log(f"⚠️ Farmer Name column not found. Using first column: '{name_col}'")
        else:
            log("❌ Excel sheet is empty or has no columns.")
            return

    # 4. Ensure output columns exist and are string-safe
    for col in ["Status", "Response", "Farmer ID"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    total_rows = len(df)
    processed_count = 0
    processed_lock = threading.Lock()

    # Count already-executed rows for resume support
    already_done = df[df['Status'].str.strip().str.lower() == 'success'].shape[0]
    log(f"📊 Total rows: {total_rows} | Already Executed: {already_done} | Pending: {total_rows - already_done}")
    log(f"🚀 Starting farmer creation with {MAX_WORKERS} workers...")

    # -------------------------------------------------
    # Worker function
    # -------------------------------------------------
    def process_farmer(index, name_val):
        if not name_val or name_val.lower() in ["nan", "none", ""]:
            log(f"⚠️ Row {index+2} skipped: Farmer Name is empty.")
            return index, "Skipped", "Empty Farmer Name", "N/A"

        log(f"🔄 Creating Farmer: {name_val} | Row {index+2}")

        # Build Payload
        farmer_payload = {
            "status": "DISABLE",
            "data": {},
            "images": {},
            "firstName": name_val,
            "farmerCode": "",
            "assignedTo": [
                {
                    "id": 1401,
                    "name": "Admin_Bat",
                    "data": {
                        "geoIds": [656497],
                        "srRegionEnabled": True
                    },
                    "assignedManagersName": [],
                    "managers": [],
                    "userStatus": None,
                    "location": None,
                    "contactNumber": "6543345612",
                    "email": "admin_bat@bat.com",
                    "preferences": {
                        "id": 1451,
                        "currency": "DOLLAR",
                        "language": "en",
                        "timeZone": "IST",
                        "areaUnits": "HECTARE",
                        "locale": "pt-BR",
                        "data": {
                            "assetTag": [],
                            "caTag": [],
                            "farmerTag": []
                        },
                        "locations": None
                    },
                    "address": None,
                    "assignedTo": None,
                    "managersName": None,
                    "companyId": 1251,
                    "parentCompanyId": None,
                    "userRoleId": 1351,
                    "userRoleName": "ROLE_ADMIN",
                    "correspondingKcId": None,
                    "resources": None,
                    "countryCode": "+55",
                    "companyStatus": None,
                    "clientId": "43243017-7e42-447b-bbfd-e5b2065a460c",
                    "images": None,
                    "companyPreferences": None,
                    "locations": {
                        "id": 1501,
                        "name": "Brazil",
                        "administrativeAreaLevel5": None,
                        "administrativeAreaLevel4": None,
                        "administrativeAreaLevel3": None,
                        "administrativeAreaLevel2": None,
                        "administrativeAreaLevel1": None,
                        "country": "Brazil",
                        "latitude": None,
                        "longitude": None,
                        "sublocalityLevel1": None,
                        "sublocalityLevel2": None,
                        "sublocalityLevel3": None,
                        "sublocalityLevel4": None,
                        "sublocalityLevel5": None,
                        "geoInfo": {
                            "type": "FeatureCollection",
                            "features": [
                                {
                                    "type": "Feature",
                                    "geometry": {
                                        "type": "Polygon",
                                        "coordinates": [[
                                            [-73.98281703987209, -34.08909995749887],
                                            [-28.65054299369068, -34.08909995749887],
                                            [-28.65054299369068, 5.270047696693523],
                                            [-73.98281703987209, 5.270047696693523],
                                            [-73.98281703987209, -34.08909995749887]
                                        ]]
                                    },
                                    "properties": {}
                                }
                            ]
                        },
                        "bounds": {
                            "southwest": {
                                "lat": -34.08909995749887,
                                "lng": -73.98281703987209
                            },
                            "northeast": {
                                "lat": 5.270047696693523,
                                "lng": -28.65054299369068
                            }
                        },
                        "placeId": "ChIJzyjM68dZnAARYz4p8gYVWik"
                    },
                    "enabled": True,
                    "isAcreSquareUser": False,
                    "isGDPRCompliant": True,
                    "lastModifiedDate": "2025-10-15T05:27:51.175Z",
                    "loginType": None,
                    "executiveRoleUser": False,
                    "preferredName": "6543345612",
                    "deviceToken": None,
                    "deviceType": None,
                    "createdBy": "SYSTEM",
                    "lastModifiedBy": "1401",
                    "deleted": False
                }
            ],
            "address": {
                "country": "Brazil",
                "formattedAddress": "Brazil",
                "administrativeAreaLevel1": "",
                "locality": "",
                "postalCode": "",
                "houseNo": "",
                "buildingName": "",
                "placeId": "ChIJzyjM68dZnAARYz4p8gYVWik",
                "latitude": -14.235004,
                "longitude": -51.92528
            },
            "isGDPRCompliant": True
        }

        multipart_data = {"dto": (None, json.dumps(farmer_payload), "application/json")}

        try:
            resp = requests.post(api_url, headers=headers, files=multipart_data)

            if resp.status_code in [200, 201]:
                farmer_id = "N/A"
                try:
                    resp_json = resp.json()
                    if isinstance(resp_json, dict):
                        farmer_id = resp_json.get("id") or resp_json.get("farmerId") or "N/A"
                    elif isinstance(resp_json, list) and len(resp_json) > 0:
                        farmer_id = resp_json[0].get("id") or resp_json[0].get("farmerId") or "N/A"
                except Exception:
                    pass
                log(f"✅ Success: Created farmer '{name_val}' with ID: {farmer_id}")
                return index, "Success", resp.text[:500], str(farmer_id)
            else:
                log(f"❌ Failed: Row {index+2} - HTTP {resp.status_code}: {resp.text[:300]}")
                return index, f"Failed: {resp.status_code}", resp.text, "N/A"

        except Exception as e:
            log(f"❌ Error: Row {index+2} - {e}")
            return index, "Error", str(e), "N/A"

    # -------------------------------------------------
    # Multithreading execution
    # -------------------------------------------------
    futures = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for index, row in df.iterrows():
            # Skip already successfully executed rows (resume support)
            current_status = str(row.get('Status', '')).strip().lower()
            if current_status == 'success':
                with processed_lock:
                    processed_count += 1
                continue

            name_val = str(row.get(name_col, "")).strip()
            futures.append(executor.submit(process_farmer, index, name_val))
            time.sleep(delay_time / MAX_WORKERS)  # Proportional stagger to prevent burst

        for future in as_completed(futures):
            index, status, response, farmer_id = future.result()
            df.at[index, 'Status'] = status
            df.at[index, 'Response'] = response
            df.at[index, 'Farmer ID'] = farmer_id

            with processed_lock:
                processed_count += 1
                pending_rows = total_rows - processed_count
                log(f"📈 Progress: {processed_count}/{total_rows} | Pending: {pending_rows}")

            # Live save after each completed future
            df.to_excel(output_excel_file, index=False)

    # Final Save & Summary
    try:
        df.to_excel(output_excel_file, index=False)
        log(f"\n🎯 Process completed. Processed: {processed_count} | Total: {total_rows}")
        log(f"💾 Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"❌ Error saving output file: {e}")
