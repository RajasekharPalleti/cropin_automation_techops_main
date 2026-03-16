import pandas as pd
import requests
import json
import time
import re

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

    user_api_url = config.get("base_api_url")
    if not user_api_url:
        user_api_url = "https://cloud.cropin.in/services/user/api/users/images"
        log(f"Using default User API URL: {user_api_url}")
    
    delay_time = float(config.get("delay_time", 1.0))

    google_api_key = config.get("x_api_key")
    if not google_api_key:
        log("❌ Missing Google Maps API Key. Please enter it in the configuration.")
        return

    def get_location_details(location_input, api_key):
        """Fetch structured location details using Google Maps API. Supports Name or Lat, Long."""
        if not location_input:
            return None
            
        base_url = "https://maps.googleapis.com/maps/api/geocode/json"
        
        # Check if input is a coordinate pair: "12.9716, 77.5946"
        is_coord = re.match(r"^-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?$", str(location_input).strip())
        
        if is_coord:
            params = {"latlng": location_input, "key": api_key}
        else:
            params = {"address": location_input, "key": api_key}

        try:
            response = requests.get(base_url, params=params)
            data = response.json()

            if data["status"] != "OK":
                error_msg = data.get("error_message", "No detailed error message provided by Google.")
                log(f"❌ Failed to get details for: {location_input} - {data.get('status')}: {error_msg}")
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
                "name": location_input if not is_coord else result.get("formatted_address", location_input)
            }
            return structured_data
        except Exception as e:
            log(f"Error fetching location: {e}")
            return None

    def parse_comma_separated_ints(val):
        if pd.isna(val) or str(val).strip() == "":
            return []
        parts = str(val).split(",")
        result = []
        for p in parts:
            p = p.strip()
            if p:
                try:
                    result.append(int(float(p)))
                except ValueError:
                    pass
        return result

    def get_value(cell):
        return None if pd.isna(cell) or str(cell).strip() == "" else str(cell).strip()

    # Processing Excel
    log(f"📂 Loading input Excel file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    columns_to_check = ["Status", "Response"]
    for col in columns_to_check:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str)

    # Explicitly cast to string after filling NaNs to prevent TypeError in newer pandas versions
    df["Status"] = df["Status"].fillna("").astype(str)
    df["Response"] = df["Response"].fillna("").astype(str)

    log(f"🔄 Processing {len(df)} rows...")

    for index, row in df.iterrows():
        try:
            # Excel Structure Logic (based on updated implementation plan)
            company_id = get_value(row.iloc[0])
            user_name = get_value(row.iloc[1])
            manager_ids_str = get_value(row.iloc[2])
            contact_number = get_value(row.iloc[3])
            user_role_id = get_value(row.iloc[4])
            email = get_value(row.iloc[5])
            country_code = get_value(row.iloc[6])
            country_iso_code = get_value(row.iloc[7])
            location_name_raw = get_value(row.iloc[8])
            
            timezone = get_value(row.iloc[9])
            language = get_value(row.iloc[10])
            currency = get_value(row.iloc[11])
            area_units = get_value(row.iloc[12])
            locale = get_value(row.iloc[13])
            
            # Optional Preferences
            plan_type_raw = get_value(row.iloc[14])
            crop_pref_raw = get_value(row.iloc[15])
            project_pref_raw = get_value(row.iloc[16])
            forms_raw = get_value(row.iloc[17])
            loc_pref_raw = get_value(row.iloc[18])
            farmer_tags_raw = get_value(row.iloc[19])
            asset_tags_raw = get_value(row.iloc[20])
            plot_tags_raw = get_value(row.iloc[21])
            precip_unit = get_value(row.iloc[22])
            temp_unit = get_value(row.iloc[23])
            weight_unit = get_value(row.iloc[24])
            geo_id_raw = get_value(row.iloc[25])

            # Validation
            if not company_id or not user_name or not email or not contact_number:
                log(f"⚠️ Row {index+2} skipped: Missing mandatory fields (Company ID, Name, Email, or Contact).")
                df.at[index, 'Status'] = "Skipped: Missing Mandatory Data"
                continue

            # Fetch Primary Location
            primary_location = get_location_details(location_name_raw, google_api_key)
            if not primary_location:
                log(f"❌ Primary Location failed for row {index+2}: {location_name_raw}")
                df.at[index, 'Status'] = "Location Error"
                continue

            # Preference Lists
            plan_type_prefs = [{"id": i} for i in parse_comma_separated_ints(plan_type_raw)]
            crop_prefs = parse_comma_separated_ints(crop_pref_raw)
            # Project logic
            project_ids = parse_comma_separated_ints(project_pref_raw)
            project_prefs = [{"id": i} for i in project_ids]
            
            form_ids = parse_comma_separated_ints(forms_raw)
            farmer_tag_ids = parse_comma_separated_ints(farmer_tags_raw)
            asset_tag_ids = parse_comma_separated_ints(asset_tags_raw)
            plot_tag_ids = parse_comma_separated_ints(plot_tags_raw)
            
            # Secondary Locations for Preferences
            loc_preferences = []
            if loc_pref_raw:
                # Use '|' as delimiter to allow commas inside location names/coordinates
                loc_list = [l.strip() for l in str(loc_pref_raw).split("|")] 
                for l_str in loc_list:
                    l_det = get_location_details(l_str, google_api_key)
                    if l_det:
                        loc_preferences.append(l_det)

            # Construct Payload
            user_payload = {
                "companyId": int(float(company_id)),
                "data": {
                    "countryIsoCode": country_iso_code
                },
                "images": {},
                "contactNumber": str(contact_number),
                "name": user_name,
                "email": email,
                "locations": primary_location,
                "assignedTo": None,
                "preferences": {
                    "timeZone": timezone or "IST",
                    "language": language or "en",
                    "currency": currency or "INR",
                    "areaUnits": area_units or "ACRE",
                    "locale": locale or "en-IN"
                }
            }
            
            # Conditionally add optional fields
            if user_role_id:
                user_payload["userRoleId"] = int(float(user_role_id))
            
            if country_code:
                user_payload["countryCode"] = f"+{country_code}" if not str(country_code).startswith("+") else country_code
            
            # Conditionally add optional managers
            managers = parse_comma_separated_ints(manager_ids_str)
            if managers:
                user_payload["managers"] = managers

            # Construct preferences.data dynamically
            pref_data = {}
            if plan_type_prefs: pref_data["planTypePreferences"] = plan_type_prefs
            if crop_prefs: pref_data["cropPreferences"] = crop_prefs
            if project_prefs: pref_data["projectPreferences"] = project_prefs
            if form_ids: pref_data["form"] = form_ids
            if farmer_tag_ids: pref_data["farmerTag"] = farmer_tag_ids
            if asset_tag_ids: pref_data["assetTag"] = asset_tag_ids
            if plot_tag_ids: pref_data["caTag"] = plot_tag_ids
            if geo_id_raw: pref_data["geoId"] = int(float(geo_id_raw))
            if precip_unit: pref_data["precipitationUnit"] = precip_unit
            if temp_unit: pref_data["tempratureUnit"] = temp_unit
            if weight_unit: pref_data["cropUnit"] = weight_unit
            
            if pref_data:
                user_payload["preferences"]["data"] = pref_data
            else:
                user_payload["preferences"]["data"] = {}

            if loc_preferences:
                user_payload["preferences"]["locations"] = loc_preferences

            headers = {'Authorization': f'Bearer {token}'}
            multipart_data = {"dto": (None, json.dumps(user_payload), "application/json")}
            
            log(f"🚀 Creating User: {user_name} (Row {index+2})")
            resp = requests.post(user_api_url, headers=headers, files=multipart_data)
            
            if resp.status_code in [200, 201]:
                log(f"✅ Created: {user_name}")
                df.at[index, 'Status'] = 'Success'
                df.at[index, 'Response'] = resp.text[:500]
            else:
                log(f"⚠️ Failed row {index+2}: {resp.status_code} - {resp.text}")
                df.at[index, 'Status'] = f"Failed: {resp.status_code}"
                df.at[index, 'Response'] = resp.text

        except Exception as e:
            log(f"❌ Error row {index+2}: {e}")
            df.at[index, 'Status'] = "Error"
            df.at[index, 'Response'] = str(e)
            
        time.sleep(delay_time)

    try:
        df.to_excel(output_excel_file, index=False)
        log(f"💾 Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"Error saving output: {e}")
