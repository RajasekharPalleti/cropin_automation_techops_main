"""
Adds new varieties or sub-varieties with location and yield details.

Inputs:
Excel file with NE Lat, NE Lng, SW Lat, SW Lng, Country, Lat, Lng, Coords JSON, Loc Name, Yield, Yield Unit, Ref Unit, CropID, ParentID, Name, Nickname, HarvestDays.
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
        log("No token provided in configuration.")
        return

    base_api_url = config.get("base_api_url", "https://cloud.cropin.in/services/farm/api/varieties")

    delay_time = float(config.get("delay_time", 0.5))  # seconds, configurable via UI

    # 2. Read Excel
    log(f"Loading input Excel file: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"Error reading Excel file: {e}")
        return

    # Add columns for output
    df['Status'] = ''
    df['Response'] = ''

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    log(f"Processing {len(df)} rows...")

    for index, row in df.iterrows():
        try:

            # Mapping based on user provided ilocs:
            # 4: NE Lat, 5: NE Lng, 6: SW Lat, 7: SW Lng
            # 8: Country, 9: Lat, 10: Lng, 11: Coords JSON
            # 12: Loc Name, 13: Yield, 15: Yield Unit, 16: Ref Unit
            # 17: CropID, 18: ParentID, 19: Name, 20: Nickname, 21: HarvestDays

            ne_lat = row.iloc[4]
            ne_lng = row.iloc[5]
            sw_lat = row.iloc[6]
            sw_lng = row.iloc[7]
            country = row.iloc[8]
            lat = row.iloc[9]
            lng = row.iloc[10]
            coords_json = row.iloc[11]
            loc_name = row.iloc[12]
            exp_yield = row.iloc[13]
            yield_unit = row.iloc[15]
            ref_unit = row.iloc[16]
            crop_id = row.iloc[17]
            parent_id = row.iloc[18]
            name = row.iloc[19]
            nickname = row.iloc[20]
            harvest_days = row.iloc[21]

            # Validate mandatory fields logic if needed, e.g. Name
            if pd.isna(name):
                 log(f"Row {index+1} skipped: Missing Name")
                 df.at[index, 'Status'] = 'Skipped'
                 df.at[index, 'Response'] = 'Missing Name'
                 continue

            # Coordinate parsing
            try:
                coords = json.loads(coords_json) if isinstance(coords_json, str) else coords_json
                if not coords:
                    coords = [] # Default or handle error
            except Exception:
                coords = [] # Handle parse error

            payload = {
                "data": {
                    "yieldPerLocation": [
                        {
                            "data": {},
                            "locations": {
                                "bounds": {
                                    "northeast": {
                                        "lat": ne_lat,
                                        "lng": ne_lng
                                    },
                                    "southwest": {
                                        "lat": sw_lat,
                                        "lng": sw_lng
                                    }
                                },
                                "country": country,
                                "administrativeAreaLevel3": "",
                                "administrativeAreaLevel1": "",
                                "placeId": "",
                                "latitude": lat,
                                "longitude": lng,
                                "geoInfo": {
                                    "type": "FeatureCollection",
                                    "features": [
                                        {
                                            "type": "Feature",
                                            "properties": {},
                                            "geometry": {
                                                "type": "Polygon",
                                                "coordinates": [coords] 
                                            }
                                        }
                                    ]
                                },
                                "name": loc_name
                            },
                            "expectedYield": exp_yield,
                            "expectedYieldQuantity": "",
                            "expectedYieldUnits": yield_unit,
                            "refrenceAreaUnits": ref_unit
                        }
                    ]
                },
                "cropId": crop_id,
                "name": name,
                "nickName": nickname,
                "expectedHarvestDays": harvest_days,
                "processStandardDeduction": None,
                "cropPrice": None,
                "cropStages": [],
                "seedGrades": [],
                "harvestGrades": [],
                "id": None,
                "varietyAdditionalAttributeList": []
            }

            # Add parentId
            if pd.notna(parent_id) and str(parent_id).strip() != '':
                payload['parentId'] = parent_id

            log(f"Adding variety: {name}...")
            response = requests.post(base_api_url, headers=headers, json=payload)

            if response.status_code == 201:
                df.at[index, 'Status'] = 'Success'
                df.at[index, 'Response'] = f"Code: {response.status_code}, Message: {response.text}"
                log(f"Success: {name}")
            else:
                df.at[index, 'Status'] = f"Failed: {response.status_code}"
                df.at[index, 'Response'] = f"Reason: {response.reason}, Message: {response.text}"
                log(f"Failed: {name} - {response.status_code}")

        except Exception as e:
            log(f"Error row {index+1}: {e}")
            df.at[index, 'Status'] = "Error"
            df.at[index, 'Response'] = str(e)
            
        time.sleep(delay_time)

    try:
        df.to_excel(output_excel_file, index=False)
        log(f"Output saved to: {output_excel_file}")
    except Exception as e:
        log(f"Error saving output: {e}")
