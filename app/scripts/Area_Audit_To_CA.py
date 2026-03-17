# Author: Rajasekhar Palleti
# Purpose: Update Area Audit for Croppable Areas
# Supports geoInfo in BOTH formats:

"""
Audits area data and updates Croppable Areas (CA).

Inputs:
Excel file with CA_id, CA_Name, area_Audit_DTO, Latitude, Longitude, and audited_count.
Supports geoInfo in BOTH formats:
1) Full GeoJSON FeatureCollection as type = featureCollection
2) Raw coordinates list [[lng, lat], ...]
3) Default cropAudited = true
4) Pass Area Unit in UI as company preffered unit.
"""

import json
import requests
import pandas as pd
import time

# ============================================================
# GEOINFO NORMALIZATION
# ============================================================
def _normalize_coords(data):
    """
    Recursively normalizes coordinates in a GeoJSON-like list structure.
    Converts strings to floats and strips whitespace.
    """
    if isinstance(data, list):
        # Check if it's a coordinate pair [lng, lat]
        if len(data) == 2 and not isinstance(data[0], (list, dict)):
            try:
                # Strip spaces and convert to float
                return [float(str(data[0]).strip()), float(str(data[1]).strip())]
            except (ValueError, TypeError):
                return data
        # Otherwise recurse
        return [_normalize_coords(item) for item in data]
    return data

def normalize_geo_info(area_Audit_DTO):
    """
    Accepts either:
    1) Full GeoJSON FeatureCollection
    2) Raw coordinates list [[lng, lat], ...]

    Returns:
        Valid GeoJSON FeatureCollection with MultiPolygon
    """
    if pd.isna(area_Audit_DTO) or area_Audit_DTO == "":
        raise ValueError("Empty GeoInfo")

    try:
        geo = json.loads(area_Audit_DTO)
    except json.JSONDecodeError:
         # Check if it looks like a list string but malformed? 
         # Or just raise
         raise ValueError("Invalid JSON format")

    # Case 1: Already valid FeatureCollection
    if isinstance(geo, dict) and geo.get("type") == "FeatureCollection":
        if "features" in geo:
            for feature in geo.get("features", []):
                geom = feature.get("geometry")
                if geom and "coordinates" in geom:
                    geom["coordinates"] = _normalize_coords(geom["coordinates"])
        return geo

    # Case 2: Raw coordinates list (e.g. [[77.5, 12.9], ...])
    if isinstance(geo, list):
        normalized_geo = _normalize_coords(geo)
        
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [[normalized_geo]]
                    }
                }
            ]
        }

    raise ValueError("Unsupported geoInfo format use [[long, lat], [...]])")


# ============================================================
# MAIN RUN FUNCTION
# ============================================================
def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    # ---------------- CONFIGURATION ----------------
    token = config.get("token")
    if not token:
        log("❌ Token missing. Exiting.")
        return

    # Use configured URL or default
    api_url = config.get("base_api_url")
    if not api_url:
        api_url = "https://cloud.cropin.in/services/farm/api/croppable-areas"
        log(f"Using default API URL: {api_url}")
    else:
        log(f"Using configured API URL: {api_url}")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "channel": "mobile"
    }

    delay_time = float(config.get("delay_time", 0.5))  # seconds, configurable via UI

    log(f"📘 Loading Excel file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    # Ensure output columns exist and are of string type to avoid TypeError
    for col in ["Status", "CA_Response"]:
        if col not in df.columns:
            df[col] = ""
        # Explicitly cast to string after filling NaNs to prevent TypeError in newer pandas versions
        df[col] = df[col].fillna("").astype(str)

    # Replace NaNs with empty string for safety in text fields, but be careful with numbers
    # df = df.fillna("") # Optional, may mess up numeric checks if not careful, sticking to per-row checks

    log(f"\n[INFO] Starting to process {len(df)} rows")

    for index, row in df.iterrows():
        # Try to use named columns if they exist, else fallback to indices as per original script
        # Original: 0=CA_id, 1=CA_Name, 2=area_Audit_DTO, 3=Latitude, 4=Longitude, 5=audited_count
        
        try:
             # Flexible column retrieval
            if "CA_id" in row: CA_id = row["CA_id"]
            else: CA_id = row.iloc[0]

            if "CA_Name" in row: CA_Name = row["CA_Name"]
            else: CA_Name = row.iloc[1]

            if "area_Audit_DTO" in row: area_Audit_DTO = row["area_Audit_DTO"]
            else: area_Audit_DTO = row.iloc[2]
            
            if "Latitude" in row: Latitude = row["Latitude"]
            else: Latitude = row.iloc[3]

            if "Longitude" in row: Longitude = row["Longitude"]
            else: Longitude = row.iloc[4]

            if "audited_count" in row: audited_count = row["audited_count"]
            else: audited_count = row.iloc[5]

            # Convert types if necessary (pandas might infer float for count)
            # CA_id might be UUID string
            
            # Basic validation
            if pd.isna(CA_id) or pd.isna(area_Audit_DTO) or str(CA_id).strip() == "":
                df.at[index, "Status"] = "Skipped: Missing Data"
                continue

            # Normalize geoInfo
            try:
                # Ensure area_Audit_DTO is string
                geo_info_str = str(area_Audit_DTO) if not isinstance(area_Audit_DTO, (dict, list)) else json.dumps(area_Audit_DTO)
                geo_info = normalize_geo_info(geo_info_str)
            except Exception as e:
                df.at[index, "Status"] = f"Invalid GeoInfo: {e}"
                continue

            log(f"🔄 Processing CA_ID: {CA_id} ({CA_Name})")

            # ---------------- GET CA ----------------
            get_endpoint = f"{api_url}/{CA_id}"
            # log(f"GET {get_endpoint}")
            get_response = requests.get(get_endpoint, headers=headers)

            if get_response.status_code != 200:
                df.at[index, "Status"] = f"GET Failed: {get_response.status_code}"
                # Handle truncated response text in Excel
                df.at[index, "CA_Response"] = get_response.text[:30000] 
                log(f"❌ GET Failed for {CA_Name}")
                continue
            
            log(f"✅ Fetched CA data for {CA_Name}")
            CA_data = get_response.json()

            # ---------------- PREPARE PAYLOAD ----------------
            try:
                audit_count_val = float(audited_count)
            except:
                audit_count_val = 0.0

            # Get unit from config (default to Hectare)
            unit_val = config.get("unit", "Hectare")

            areaAudit = {
                "id": None,
                "geoInfo": geo_info,
                "latitude": Latitude,
                "longitude": Longitude,
                "altitude": None
            }

            auditedArea = {
                "count": audit_count_val,
                "unit": unit_val
            }

            CA_data["areaAudit"] = areaAudit
            CA_data["auditedArea"] = auditedArea
            # Resetting lat/long at root level as per user script
            CA_data["latitude"] = None
            CA_data["longitude"] = None
            
            # CA_data["cropAudited"] = True  # Logic moved to config
            force_crop_audited = config.get("force_crop_audited", "true")
            
            if force_crop_audited == "true":
                CA_data["cropAudited"] = True
            elif force_crop_audited == "false":
                CA_data["cropAudited"] = False
            # if "none", do nothing (don't send/don't override)

            # ---------------- PUT UPDATE ----------------
            put_endpoint = f"{api_url}/area-audit"
            # log(f"PUT {put_endpoint}")
            
            put_response = requests.put(
                put_endpoint,
                headers=headers,
                data=json.dumps(CA_data)
            )

            if put_response.status_code != 200:
                df.at[index, "Status"] = f"PUT Failed: {put_response.status_code}"
                df.at[index, "CA_Response"] = put_response.text[:30000]
                log(f"❌ PUT Failed: {put_response.status_code}")
                continue

            df.at[index, "Status"] = "Success"
            df.at[index, "CA_Response"] = put_response.text[:30000]
            log(f"✅ Updated area audit for {CA_Name}")

        except requests.exceptions.RequestException as e:
            df.at[index, "Status"] = f"Request Failed: {e}"
            df.at[index, "CA_Response"] = str(e)
            log(f"❌ Request Exception: {e}")
        except Exception as e:
            df.at[index, "Status"] = f"Error: {e}"
            log(f"❌ Error: {e}")

        time.sleep(delay_time)

    # Save output
    log(f"\n💾 Saving output to: {output_excel_file}")
    try:
        df.to_excel(output_excel_file, index=False)
        log(f"🎯 Done. Output saved.")
    except Exception as e:
        log(f"❌ Error saving file: {e}")
