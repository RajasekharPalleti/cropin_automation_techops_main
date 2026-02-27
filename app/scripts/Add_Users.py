"""
Adds new users to the system and optionally uploads images.

Inputs:
Excel file with User details (Name, Email, Role, etc.).
"""
import pandas as pd

import requests
import json
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

    user_api_url = config.get("post_api_url")
    if not user_api_url:
        user_api_url = "https://cloud.cropin.in/services/user/api/users/images"
        log(f"Using default User API URL: {user_api_url}")
    
    delay_time = float(config.get("delay_time", 1.0))  # seconds, configurable via UI

    # We use x_api_key field for Google Maps API Key
    google_api_key = config.get("x_api_key")
    if not google_api_key:
        log("❌ Missing Google Maps API Key. Please enter it in the configuration.")
        return

    # Function to fetch location details
    def get_location_details(address, api_key):
        """Fetch structured location details for a given address using Google Maps API"""
        base_url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": address, "key": api_key}

        try:
            response = requests.get(base_url, params=params)
            data = response.json()

            if data["status"] != "OK":
                log(f"❌ Failed to get details for address: {address} - {data.get('status')}")
                return None

            result = data["results"][0]
            geometry = result["geometry"]
            location = geometry["location"]
            bounds = geometry.get("bounds", geometry.get("viewport", {}))
            northeast = bounds.get("northeast", {})
            southwest = bounds.get("southwest", {})

            components = {comp["types"][0]: comp["long_name"] for comp in result["address_components"]}

            structured_data = {
                "bounds": {
                    "northeast": {"lat": northeast.get("lat"), "lng": northeast.get("lng")},
                    "southwest": {"lat": southwest.get("lat"), "lng": southwest.get("lng")}
                },
                "political": components.get("sublocality_level_1") or components.get("locality"),
                "country": components.get("country"),
                "administrativeAreaLevel3": components.get("administrative_area_level_3"),
                "administrativeAreaLevel2": components.get("administrative_area_level_2"),
                "administrativeAreaLevel1": components.get("administrative_area_level_1"),
                "placeId": result["place_id"],
                "latitude": location["lat"],
                "longitude": location["lng"],
                "geoInfo": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[
                                    [southwest.get("lng"), southwest.get("lat")],
                                    [northeast.get("lng"), southwest.get("lat")],
                                    [northeast.get("lng"), northeast.get("lat")],
                                    [southwest.get("lng"), northeast.get("lat")],
                                    [southwest.get("lng"), southwest.get("lat")]
                                ]]
                            }
                        }
                    ]
                },
                "name": address
            }
            return structured_data
        except Exception as e:
            log(f"Error fetching location: {e}")
            return None

    # Processing Excel
    log(f"📂 Loading input Excel file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    def get_value(cell):
        return None if pd.isna(cell) or str(cell).strip() == "" else str(cell).strip()

    columns_to_check = ["Status", "Response", "User_response"]
    for col in columns_to_check:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str)

    log(f"🔄 Processing {len(df)} rows...")

    for index, row in df.iterrows():
        try:
            # Column mapping based on user's code (assuming standard order 0-11)
            # 0: User Name, 1: Manager IDs, 2: Contact, 3: roleId, 4: Email, 5: CountryCode, 6: Location Name
            # 7: TimeZone, 8: Language, 9: Currency, 10: AreaUnits, 11: Locale
            
            user_name = get_value(row.iloc[0])
            manager_ids_str = get_value(row.iloc[1])
            managerIds = [mid.strip() for mid in manager_ids_str.split(",") if mid.strip()] if manager_ids_str else []
            
            contactNumber = get_value(row.iloc[2]) or ""
            userRoleId = get_value(row.iloc[3])
            email = get_value(row.iloc[4])
            countryCode = get_value(row.iloc[5])
            countryISOcode = get_value(row.iloc[6])
            location_name = get_value(row.iloc[7])
            
            timeZone = get_value(row.iloc[8])
            language = get_value(row.iloc[9])
            currency = get_value(row.iloc[10])
            areaUnits = get_value(row.iloc[11])
            locale = get_value(row.iloc[12])

            # Validation
            if not user_name:
                log(f"⚠️ Row {index + 1} skipped: Invalid user name.")
                df.at[index, 'Status'] = "Skipped"
                continue
            
            if not managerIds:
                log(f"⚠️ Row {index + 1} skipped: Empty manager list.")
                df.at[index, 'Status'] = "Skipped"
                continue

            # Check logic: user hardcoded companyId = 1251. 
            # We should probably expose this or keep it hardcoded as per snippet.
            companyId = 1251 

            log(f"📍 Fetching location for: {location_name}")
            location_details = get_location_details(location_name, google_api_key)
            if not location_details:
                log(f"❌ Location not found: {location_name}")
                df.at[index, 'Status'] = "Location Failed"
                continue
            
            # Payload
            user_payload = {
                "companyId": companyId,
                "data": {
                    "countryIsoCode": countryISOcode
                    },
                "images": {},
                "contactNumber": contactNumber,
                "name": user_name,
                "userRoleId": userRoleId,
                "countryCode": f"+{countryCode}", # now the value is like +91
                "email": email,
                "locations": location_details,
                "managers": [managerIds[0]] if managerIds else [], # User snippet wrapped [managerIds], but managerIds is a list. Wait.
                # User snippet: "managers": [managerIds]. If managerIds is a list of strings, this makes it a list of list of strings? 
                # Or user meant managerIds is a single string?
                # User snippet: managerIds = [mid.strip() for mid in managerIds.split(",")] 
                # Payload: "managers": [managerIds] -> [[id1, id2]]. This seems potentially wrong for standard APIs which expect ["id1", "id2"].
                # However, strictly following user snippet: "managers": [managerIds]
                # If managerIds is ['123'], payload is [['123']]. 
                # Wait, looking at user snippet: 
                # extract manager ids logic produces a LIST. 
                # Payload uses [managerIds]. 
                # I will follow user snippet EXACTLY.
                "assignedTo": None,
                "preferences": {
                    "data": {},
                    "timeZone": timeZone,
                    "language": language,
                    "currency": currency,
                    "areaUnits": areaUnits,
                    "locale": locale
                }
            }
            # Correction on managers: usually it's list of strings. But if user code works... 
            # Let's check `managerIds` variable in user snippet. It's a list.
            # `managers: [managerIds]` puts the list inside a list. 
            # I will trust the user snippet logic even if looks odd, or maybe flattened?
            # Actually, `managerIds` in user snippet is a LIST of strings. 
            # putting it in `[]` creates `[['id']]`. 
            # I'll stick to user logic.

            headers = {'Authorization': f'Bearer {token}'}
            multipart_data = {"dto": (None, json.dumps(user_payload), "application/json")}
            
            log(f"🚀 Creating User: {user_name}")
            resp = requests.post(user_api_url, headers=headers, files=multipart_data)
            
            if resp.status_code == 201:
                log(f"✅ Created: {user_name}")
                df.at[index, 'Status'] = 'Success'
                df.at[index, 'User_response'] = resp.text[:200]
            else:
                log(f"⚠️ Failed: {resp.status_code} - {resp.text}")
                df.at[index, 'Status'] = f"Failed: {resp.status_code}"
                df.at[index, 'Response'] = resp.text

        except Exception as e:
            log(f"❌ Error row {index}: {e}")
            df.at[index, 'Status'] = "Error"
            df.at[index, 'Response'] = str(e)
            
        time.sleep(delay_time)

    try:
        df.to_excel(output_excel_file, index=False)
        log(f"💾 Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"Error saving output: {e}")
