"""
Add Geotag or Update Lat Long to CA.

Inputs:
Excel file with columns:
Column A: CA_ID, 
Column B is Optional, 
Column C: Latitude, 
Column D: Longitude
"""

import json
import requests
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def run(input_excel, output_excel, config, log_callback=None):
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    token = config.get("token")
    api_url = config.get("url")
    worker_count = config.get("worker_count", 2)
    thread_delay = float(config.get("delay_time", 1))
    
    if not api_url:
        api_url = "https://cloud.cropin.in/services/farm/api/croppable-areas"

    if not token:
        log("Error: Missing authentication token.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "channel": "mobile"
    }

    log(f"Reading input file: {input_excel}")
    try:
        df = pd.read_excel(input_excel)
    except Exception as e:
        log(f"Error reading Excel file: {e}")
        return

    if "Status" not in df.columns:
        df["Status"] = ""
    if "CA_Response" not in df.columns:
        df["CA_Response"] = ""

    total_rows = len(df)
    log(f"Processing {total_rows} rows with {worker_count} workers. Delay: {thread_delay}s")

    # Helper function to process a single row
    def process_row(index, row):
        result = {"index": index, "status": "", "response": ""}
        try:
            # Row access logic: A=0, C=2, D=3.
            if len(row) < 4:
                return {"index": index, "status": "Skipped: Row has insufficient columns", "response": ""}

            CA_id = row.iloc[0]
            Latitude = row.iloc[2]
            Longitude = row.iloc[3]

            if pd.isna(CA_id) or pd.isna(Latitude) or pd.isna(Longitude):
                return {"index": index, "status": "Skipped: Missing Data (CA_ID, Lat, or Long)", "response": ""}

            # Delay before GET
            time.sleep(thread_delay)
            # GET
            get_response = requests.get(f"{api_url}/{CA_id}", headers=headers)
            if get_response.status_code != 200:
                log(f"Row {index + 2}: GET Failed ({get_response.status_code}) for CA_ID: {CA_id}")
                return {"index": index, "status": f"GET Failed: {get_response.status_code}", "response": ""}

            CA_data = get_response.json()
            
            # Update fields
            CA_data["latitude"] = Latitude
            CA_data["longitude"] = Longitude

            if ("areaAudit" in CA_data and CA_data["areaAudit"] is not None 
                and isinstance(CA_data["areaAudit"], dict)
                and CA_data["areaAudit"].get("latitude") is not None):
                
                CA_data["areaAudit"]["latitude"] = Latitude
                CA_data["areaAudit"]["longitude"] = Longitude
                CA_data["cropAudited"] = True
            else:
                CA_data["areaAudit"] = {
                    "geoInfo": {
                        "type": "FeatureCollection",
                        "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "MultiPolygon", "coordinates": []}}]
                    },
                    "latitude": Latitude,
                    "longitude": Longitude,
                    "altitude": None
                }
                CA_data["cropAudited"] = False

            # Delay before PUT
            time.sleep(thread_delay) # configured delay
            
            # PUT
            put_response = requests.put(f"{api_url}/area-audit", headers=headers, data=json.dumps(CA_data))
            
            if put_response.status_code in (200, 204):
                log(f"Row {index + 2}: Success for CA_ID: {CA_id}")
                return {"index": index, "status": "Success", "response": put_response.text}
            else:
                log(f"Row {index + 2}: PUT Failed ({put_response.status_code}) for CA_ID: {CA_id}")
                return {"index": index, "status": "Failed", "response": put_response.text}

        except Exception as e:
            log(f"Row {index + 2}: Exception: {e}")
            return {"index": index, "status": f"Failed: {str(e)}", "response": ""}

    # Execute with ThreadPool
    with ThreadPoolExecutor(max_workers=int(worker_count)) as executor:
        futures = {executor.submit(process_row, index, row): index for index, row in df.iterrows()}
        
        for future in as_completed(futures):
            res = future.result()
            idx = res["index"]
            df.at[idx, "Status"] = res["status"]
            df.at[idx, "CA_Response"] = res["response"]

    # Save output
    try:
        df.to_excel(output_excel, index=False)
        log(f"Output saved to {output_excel}")
    except Exception as e:
        log(f"Error saving output Excel: {e}")
