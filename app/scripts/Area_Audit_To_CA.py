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

    total_rows = len(df)
    processed_count = 0
    import threading
    from concurrent.futures import ThreadPoolExecutor
    processed_lock = threading.Lock()
    
    MAX_WORKERS = int(config.get("worker_count", 1))
    log(f"\n[INFO] Starting to process {total_rows} rows with {MAX_WORKERS} workers")

    # Split DataFrame into chunks
    chunk_size = (total_rows + MAX_WORKERS - 1) // MAX_WORKERS if MAX_WORKERS > 0 else total_rows
    chunks = [df.iloc[i:i + chunk_size].copy() for i in range(0, total_rows, chunk_size)]
    actual_workers = min(len(chunks), MAX_WORKERS) if MAX_WORKERS > 0 else 1

    def process_chunk(df_chunk, thread_id):
        nonlocal processed_count
        results = []

        for index, row in df_chunk.iterrows():
            try:
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

                if pd.isna(CA_id) or pd.isna(area_Audit_DTO) or str(CA_id).strip() == "":
                    results.append((index, "Skipped: Missing Data", ""))
                    continue

                try:
                    geo_info_str = str(area_Audit_DTO) if not isinstance(area_Audit_DTO, (dict, list)) else json.dumps(area_Audit_DTO)
                    geo_info = normalize_geo_info(geo_info_str)
                except Exception as e:
                    results.append((index, f"Invalid GeoInfo: {e}", ""))
                    continue

                with processed_lock:
                    pending_rows = total_rows - processed_count

                log(f"[Thread {thread_id}] 🔄 Processing CA_ID: {CA_id} ({CA_Name}) | Row {index + 1}/{total_rows} | Processed: {processed_count} | Pending: {pending_rows}")

                get_endpoint = f"{api_url}/{CA_id}"
                get_response = requests.get(get_endpoint, headers=headers)

                if get_response.status_code != 200:
                    results.append((index, f"GET Failed: {get_response.status_code}", get_response.text[:30000]))
                    log(f"[Thread {thread_id}] ❌ GET Failed for {CA_Name}")
                    continue
                
                log(f"[Thread {thread_id}] ✅ Fetched CA data for {CA_Name}")
                CA_data = get_response.json()

                try:
                    audit_count_val = float(audited_count)
                except:
                    audit_count_val = 0.0

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
                CA_data["latitude"] = None
                CA_data["longitude"] = None
                
                force_crop_audited = config.get("force_crop_audited", "true")
                
                if force_crop_audited == "true":
                    CA_data["cropAudited"] = True
                elif force_crop_audited == "false":
                    CA_data["cropAudited"] = False

                put_endpoint = f"{api_url}/area-audit"
                
                put_response = requests.put(
                    put_endpoint,
                    headers=headers,
                    data=json.dumps(CA_data)
                )

                if put_response.status_code != 200:
                    results.append((index, f"PUT Failed: {put_response.status_code}", put_response.text[:30000]))
                    log(f"[Thread {thread_id}] ❌ PUT Failed: {put_response.status_code}")
                    continue

                results.append((index, "Success", put_response.text[:30000]))
                log(f"[Thread {thread_id}] ✅ Updated area audit for {CA_Name}")

            except requests.exceptions.RequestException as e:
                results.append((index, f"Request Failed: {e}", str(e)))
                log(f"[Thread {thread_id}] ❌ Request Exception: {e}")
            except Exception as e:
                results.append((index, f"Error: {e}", ""))
                log(f"[Thread {thread_id}] ❌ Error: {e}")

            with processed_lock:
                processed_count += 1
            time.sleep(delay_time)

        return results

    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        futures = [
            executor.submit(process_chunk, chunk, thread_id + 1)
            for thread_id, chunk in enumerate(chunks)
        ]
        chunk_results = []
        for future in futures:
            chunk_results.extend(future.result())

    log("💾 Aggregating results...")
    for idx, status, response in chunk_results:
        if idx in df.index:
            df.at[idx, "Status"] = status
            df.at[idx, "CA_Response"] = str(response)

    # Save output
    log(f"\n💾 Saving output to: {output_excel_file}")
    try:
        df.to_excel(output_excel_file, index=False)
        log(f"🎯 Done. Output saved.")
    except Exception as e:
        log(f"❌ Error saving file: {e}")
