"""
Creates places by taking 'Place name', 'Place type', 'Latitude', and 'Longitude' from an Excel file,
fetching the corresponding address from Google Maps API, and submitting it to the Cropin API.

Author: Rajasekhar Palleti

Inputs:
Excel file with 'Place name', 'Place type', 'Latitude', and 'Longitude' columns.
"""

import time
import requests
import json
import pandas as pd

def get_address_data(session: requests.Session, lat: float, lng: float, google_api_key: str) -> dict:
    if not google_api_key:
        raise RuntimeError("Google API key is missing. Set Google API Key in config before running.")

    params = {
        "latlng": f"{lat},{lng}",
        "key": google_api_key,
        "result_type": "street_address|premise|sublocality|locality",
    }

    resp = session.get("https://maps.googleapis.com/maps/api/geocode/json", params=params, timeout=10)
    data = resp.json()

    if data.get("status") != "OK" or not data.get("results"):
        error_msg = data.get("error_message", "No detailed error message provided by Google.")
        raise RuntimeError(f"Google API returned {data.get('status')} - {error_msg}")

    result = data["results"][0]
    formatted_address = result.get("formatted_address", "")

    comps_raw = result.get("address_components", [])
    comps = {
        "country": "",
        "administrativeAreaLevel1": "",
        "administrativeAreaLevel2": "",
        "locality": "",
        "sublocalityLevel1": "",
        "sublocalityLevel2": "",
        "postalCode": "",
    }

    for c in comps_raw:
        t = c.get("types", [])
        if "country" in t:
            comps["country"] = c.get("long_name", "")
        elif "administrative_area_level_1" in t:
            comps["administrativeAreaLevel1"] = c.get("long_name", "")
        elif "administrative_area_level_2" in t:
            comps["administrativeAreaLevel2"] = c.get("long_name", "")
        elif "locality" in t:
            comps["locality"] = c.get("long_name", "")
        elif "sublocality_level_1" in t:
            comps["sublocalityLevel1"] = c.get("long_name", "")
        elif "sublocality_level_2" in t:
            comps["sublocalityLevel2"] = c.get("long_name", "")
        elif "postal_code" in t:
            comps["postalCode"] = c.get("long_name", "")

    geometry = result.get("geometry", {}).get("location", {})
    glat = geometry.get("lat", lat)
    glng = geometry.get("lng", lng)

    return {
        "country": comps["country"],
        "formattedAddress": formatted_address,
        "administrativeAreaLevel1": comps["administrativeAreaLevel1"],
        "administrativeAreaLevel2": comps["administrativeAreaLevel2"],
        "locality": comps["locality"],
        "sublocalityLevel1": comps["sublocalityLevel1"],
        "sublocalityLevel2": comps["sublocalityLevel2"],
        "landmark": "",
        "postalCode": comps["postalCode"],
        "houseNo": "",
        "buildingName": "",
        "placeId": result.get("place_id", ""),
        "latitude": glat,
        "longitude": glng,
    }


def build_payload(place_name: str, place_type: str, address_data: dict) -> dict:
    return {
        "data": None,
        "name": place_name,
        "type": place_type,
        "address": address_data,
        "latitude": address_data["latitude"],
        "longitude": address_data["longitude"],
    }


def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    api_url = config.get("base_api_url", "https://cloud.cropin.in/services/farm/api/place")
    google_api_key = config.get("x_api_key")  # Sourced from 'google_api' extended_config_type
    token = config.get("token")
    delay_time = float(config.get("delay_time", 1.0))

    if not token:
        log("Error: Authorization token missing.")
        return
        
    if not google_api_key:
        log("Error: Google API Key missing. Please provide it in the UI.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    log(f"Reading input file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"Failed to read Excel: {e}")
        return

    # Add columns for output and ensure string type for safety
    for col in ["Status", "Failure Reason", "Place ID"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    # Identifiers for required columns
    required_cols = ["Place name", "Place type", "Latitude", "Longitude"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    
    if missing_cols:
        log(f"Error: Missing required columns in Excel: {', '.join(missing_cols)}")
        return

    session = requests.Session()
    total_rows = len(df)
    processed_count = 0
    log(f"Starting place creation for {total_rows} rows...")

    for index, row in df.iterrows():
        place_name = row["Place name"]
        place_type = row["Place type"]
        lat = row["Latitude"]
        lng = row["Longitude"]

        if pd.isna(place_name) or pd.isna(place_type) or pd.isna(lat) or pd.isna(lng):
            df.at[index, "Status"] = "Skipped"
            df.at[index, "Failure Reason"] = "Missing required fields"
            continue
            
        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except ValueError:
            df.at[index, "Status"] = "Failed"
            df.at[index, "Failure Reason"] = "Latitude or Longitude is not a valid number"
            continue

        pending_rows = total_rows - processed_count
        log(f"📍 Executing Row {index + 1} of {total_rows}: Creating place '{place_name}' | Processed: {processed_count} | Pending: {pending_rows}")

        try:
            # 1. Fetch Address
            address_data = get_address_data(session, lat_f, lng_f, google_api_key)
            
            # 2. Build Payload
            payload = build_payload(str(place_name), str(place_type), address_data)

            # 3. Create Place
            resp = session.post(
                api_url,
                headers=headers,
                data=json.dumps(payload),
                timeout=30,
            )
            
            if resp.status_code in (200, 201):
                try:
                    data = resp.json()
                    pid = data.get("id") or data.get("data", {}).get("id")
                    df.at[index, "Status"] = "Success"
                    if pid:
                        df.at[index, "Place ID"] = str(pid)
                        log(f"   ✅ Successfully created place → ID: {pid}")
                    else:
                        log("   ✅ Success but failed to extract ID from JSON")
                except Exception:
                    df.at[index, "Status"] = "Success (JSON Parse Failed)"
                    log("   ⚠️ Created but JSON parse failed")
            else:
                err_text = resp.text[:200]
                df.at[index, "Status"] = "Failed"
                df.at[index, "Failure Reason"] = f"HTTP {resp.status_code}: {err_text}"
                log(f"   ❌ Failed ({resp.status_code}) → {err_text}")

        except Exception as e:
            df.at[index, "Status"] = "Failed"
            df.at[index, "Failure Reason"] = str(e)
            log(f"   ❌ Error: {str(e)}")

        processed_count += 1
        time.sleep(delay_time)

    try:
        df.to_excel(output_excel_file, index=False)
        log(f"✅ Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"❌ Error saving output: {e}")
