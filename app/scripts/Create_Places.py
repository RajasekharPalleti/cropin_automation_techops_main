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
import re

try:
    from global_land_mask import globe
    HAS_GLOBAL_LAND_MASK = True
except ImportError:
    HAS_GLOBAL_LAND_MASK = False

def parse_coordinate(coord_str) -> float:
    """Parses various coordinate formats (DD, DMS, DDM) into decimal degrees."""
    if pd.isna(coord_str) or str(coord_str).strip() == "":
        raise ValueError("Coordinate is empty")
        
    coord_str = str(coord_str).strip().upper()
    
    # If the coordinate ends with 'O' (Oeste), replace it with 'W' (West)
    if coord_str.endswith('O'):
        coord_str = coord_str[:-1] + 'W'
        
    # Replace comma with period for decimals
    coord_str = coord_str.replace(',', '.')
    
    # Replace common typography to spaces for easier splitting
    clean_str = coord_str.replace("''", '"').replace('′', "'").replace('″', '"').replace('°', ' ')
    
    direction_multiplier = 1
    if 'S' in clean_str or 'W' in clean_str:
        direction_multiplier = -1
    elif clean_str.startswith('-') and 'S' not in clean_str and 'W' not in clean_str:
        direction_multiplier = -1
        
    # Extract numbers
    parts = re.findall(r"[\d\.]+", clean_str)
    if not parts:
        raise ValueError(f"No numbers found in {coord_str}")
        
    nums = [float(p) for p in parts]
    
    dd = nums[0]
    if len(nums) > 1:
        dd += nums[1] / 60.0
    if len(nums) > 2:
        dd += nums[2] / 3600.0
        
    return dd * direction_multiplier

def get_elevation(session: requests.Session, lat: float, lng: float, google_api_key: str) -> float | None:
    """Fetches elevation in meters from Google Maps Elevation API if available."""
    if not google_api_key:
        return None
    try:
        url = "https://maps.googleapis.com/maps/api/elevation/json"
        resp = session.get(url, params={"locations": f"{lat},{lng}", "key": google_api_key}, timeout=10)
        data = resp.json()
        if data.get("status") == "OK" and data.get("results"):
            return float(data["results"][0].get("elevation", 0.0))
    except Exception:
        pass
    return None

def get_address_data(session: requests.Session, lat: float, lng: float, google_api_key: str) -> dict:
    if not google_api_key:
        raise RuntimeError("Google API key is missing. Set Google API Key in config before running.")

    params = {
        "latlng": f"{lat},{lng}",
        "key": google_api_key
        # Removed 'result_type' filter because rural/farm coordinates often don't have a 
        # formal 'street_address' or 'locality', which causes ZERO_RESULTS errors.
    }

    try:
        resp = session.get("https://maps.googleapis.com/maps/api/geocode/json", params=params, timeout=10)
        data = resp.json()
        if data.get("status") != "OK":
            print(f"⚠️ Google API returned non-OK status: {data.get('status')} - {data.get('error_message', 'No details')}")
    except Exception as e:
        print(f"⚠️ Google API request failed: {e}")
        data = {}

    comps = {
        "country": "",
        "administrativeAreaLevel1": "",
        "administrativeAreaLevel2": "",
        "locality": "",
        "sublocalityLevel1": "",
        "sublocalityLevel2": "",
        "postalCode": "",
    }
    
    formatted_address = ""
    place_id = ""
    is_water_body = False
    water_body_name = ""
    is_extreme_peak = False
    peak_name = ""

    water_keywords = {
        "ocean", "sea", "bay", "gulf", "strait", "lake", "reservoir", 
        "river", "channel", "lagoon", "estuary", "sound", "cove", "water"
    }
    peak_types = {"glacier", "col"}
    peak_keywords = {"glacier", "peak", "volcano"}

    if data.get("status") == "OK" and data.get("results"):
        results = data["results"]
        # Take the most specific address and place ID from the first result
        formatted_address = results[0].get("formatted_address", "")
        place_id = results[0].get("place_id", "")
        
        # Iterate through all results to detect water bodies, peaks, and collect address components
        for result in results:
            res_types = set(result.get("types", []))
            res_addr = result.get("formatted_address", "")
            addr_words = set(re.findall(r"\b[a-zA-Z]+\b", res_addr.lower()))

            # Check address components
            comps_raw = result.get("address_components", [])
            for c in comps_raw:
                t = set(c.get("types", []))
                c_name = c.get("long_name", "")
                c_words = set(re.findall(r"\b[a-zA-Z]+\b", c_name.lower()))

                # Detect water bodies in components or results
                if "natural_feature" in t or "natural_feature" in res_types or "water" in res_types or "water" in t:
                    if c_words & water_keywords or addr_words & water_keywords:
                        is_water_body = True
                        if not water_body_name:
                            water_body_name = c_name or res_addr

                # Detect extreme peaks / glaciers in components
                if "natural_feature" in t or "natural_feature" in res_types or t & peak_types or res_types & peak_types:
                    if c_words & peak_keywords or addr_words & peak_keywords or t & peak_types or res_types & peak_types:
                        is_extreme_peak = True
                        if not peak_name:
                            peak_name = c_name or res_addr

                # Collect address components if not already filled
                if "country" in t and not comps["country"]:
                    comps["country"] = c_name
                elif "administrative_area_level_1" in t and not comps["administrativeAreaLevel1"]:
                    comps["administrativeAreaLevel1"] = c_name
                elif "administrative_area_level_2" in t and not comps["administrativeAreaLevel2"]:
                    comps["administrativeAreaLevel2"] = c_name
                elif "locality" in t and not comps["locality"]:
                    comps["locality"] = c_name
                elif "sublocality_level_1" in t and not comps["sublocalityLevel1"]:
                    comps["sublocalityLevel1"] = c_name
                elif "sublocality_level_2" in t and not comps["sublocalityLevel2"]:
                    comps["sublocalityLevel2"] = c_name
                elif "postal_code" in t and not comps["postalCode"]:
                    comps["postalCode"] = c_name

            # Check top-level result types and address
            if "natural_feature" in res_types or "water" in res_types:
                if addr_words & water_keywords:
                    is_water_body = True
                    if not water_body_name:
                        water_body_name = res_addr
                if addr_words & peak_keywords or res_types & peak_types:
                    is_extreme_peak = True
                    if not peak_name:
                        peak_name = res_addr

    # Always use the EXACT original coordinates.
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
        "placeId": place_id,
        "latitude": lat,
        "longitude": lng,
        "is_water_body": is_water_body,
        "water_body_name": water_body_name,
        "is_extreme_peak": is_extreme_peak,
        "peak_name": peak_name,
        "is_natural_feature": is_water_body,
    }


def build_payload(place_name: str, place_type: str, address_data: dict, tags: list) -> dict:
    # Filter out internal validation flags before passing address to Cropin API
    clean_address = {
        k: v for k, v in address_data.items()
        if not k.startswith("is_") and not k.endswith("_name")
    }
    payload = {
        "name": place_name,
        "type": place_type,
        "address": clean_address,
        "latitude": address_data["latitude"],
        "longitude": address_data["longitude"],
    }
    
    # Only attach tags if they are actually provided
    if tags:
        payload["data"] = {"tags": tags}
    else:
        payload["data"] = None
        
    return payload


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
    for col in ["Status", "Failure Reason", "Place ID", "Response"]:
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
    
    # Identify the tags column (flexible matching)
    tags_col = None
    for col in df.columns:
        if "tag" in str(col).lower():
            tags_col = col
            break
            
    if tags_col:
        log(f"Found tags column in Excel: '{tags_col}'")
    else:
        log("Warning: No column containing 'tag' found in Excel. Tags will not be created.")

    def clean_val(val):
        if pd.isna(val):
            return ""
        if isinstance(val, float) and val.is_integer():
            return str(int(val))
        return str(val).strip()

    def parse_tag(t):
        t = t.strip()
        if t.isdigit():
            return int(t)
        try:
            return float(t)
        except ValueError:
            return t

    for index, row in df.iterrows():
        place_name = clean_val(row.get("Place name"))
        place_type = clean_val(row.get("Place type"))
        lat = clean_val(row.get("Latitude"))
        lng = clean_val(row.get("Longitude"))
        
        tags_raw = clean_val(row.get(tags_col)) if tags_col else ""
        tags_list = [parse_tag(t) for t in tags_raw.split(",")] if tags_raw else []

        # If required fields are missing/empty, gracefully skip the row
        if not place_name or not place_type or not lat or not lng:
            df.at[index, "Status"] = "Skipped"
            df.at[index, "Failure Reason"] = "Missing required fields"
            log(f"⏭️  Skipped Row {index + 1}: Missing one or more required fields (Name, Type, Lat, or Lng)")
            continue
            
        try:
            lat_f = parse_coordinate(lat)
            lng_f = parse_coordinate(lng)
            if not (-90.0 <= lat_f <= 90.0):
                raise ValueError(f"Latitude {lat_f} is out of valid range (-90 to 90)")
            if not (-180.0 <= lng_f <= 180.0):
                raise ValueError(f"Longitude {lng_f} is out of valid range (-180 to 180)")
        except Exception as e:
            df.at[index, "Status"] = "Failed"
            df.at[index, "Failure Reason"] = f"Coordinate format error: {e}"
            log(f"   ❌ Coordinate Error: {e}")
            continue

        pending_rows = total_rows - processed_count
        log(f"📍 Executing Row {index + 1} of {total_rows}: Creating place '{place_name}' | Processed: {processed_count} | Pending: {pending_rows}")

        # Fast Pre-Check: Instant Ocean / Sea detection via global-land-mask
        if HAS_GLOBAL_LAND_MASK and globe.is_ocean(lat_f, lng_f):
            df.at[index, "Status"] = "Failed"
            df.at[index, "Failure Reason"] = "Coordinate is located in an ocean or sea"
            log("   ❌ Failed: Coordinate is located in an ocean or sea")
            processed_count += 1
            time.sleep(delay_time)
            continue

        try:
            # 1. Fetch Address
            address_data = get_address_data(session, lat_f, lng_f, google_api_key)
            
            # Block addresses that are explicitly inland water bodies (lakes, rivers, reservoirs, bays)
            if address_data.get("is_water_body"):
                body_name = address_data.get("water_body_name") or "water body"
                df.at[index, "Status"] = "Failed"
                df.at[index, "Failure Reason"] = f"Coordinate is located in a body of water ({body_name})"
                log(f"   ❌ Failed: Coordinate is located in a body of water ({body_name})")
                processed_count += 1
                time.sleep(delay_time)
                continue

            # Block addresses that are explicitly uncultivable mountain peaks or glaciers
            if address_data.get("is_extreme_peak"):
                peak_desc = address_data.get("peak_name") or "mountain peak / glacier"
                df.at[index, "Status"] = "Failed"
                df.at[index, "Failure Reason"] = f"Coordinate is located on an uncultivable feature ({peak_desc})"
                log(f"   ❌ Failed: Coordinate is located on an uncultivable feature ({peak_desc})")
                processed_count += 1
                time.sleep(delay_time)
                continue

            # Check elevation for extreme altitude (> 3,000m uncultivable mountain peak)
            elevation = get_elevation(session, lat_f, lng_f, google_api_key)
            if elevation is not None and elevation > 3000:
                df.at[index, "Status"] = "Failed"
                df.at[index, "Failure Reason"] = f"Coordinate is at extreme altitude / mountain peak ({elevation:.0f}m above sea level)"
                log(f"   ❌ Failed: Coordinate is at extreme altitude / mountain peak ({elevation:.0f}m)")
                processed_count += 1
                time.sleep(delay_time)
                continue

            # Address Validation: formattedAddress, country, and locality are MANDATORY
            f_addr = address_data.get("formattedAddress", "").strip()
            country = address_data.get("country", "").strip()
            locality = address_data.get("locality", "").strip()
            
            # Fallback for missing locality (common in rural farm areas)
            if not locality:
                locality = address_data.get("administrativeAreaLevel2", "").strip() or address_data.get("administrativeAreaLevel1", "").strip()
                address_data["locality"] = locality
            
            if not f_addr or not country or not locality:
                df.at[index, "Status"] = "Failed"
                df.at[index, "Failure Reason"] = "Failed to fetch the address with the co ordinates"
                log("   ❌ Failed: Failed to fetch the address with the co ordinates")
                processed_count += 1
                time.sleep(delay_time)
                continue
            
            # 2. Build Payload
            payload = build_payload(str(place_name), str(place_type), address_data, tags_list)

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
                    df.at[index, "Response"] = json.dumps(data)
                    if pid:
                        df.at[index, "Place ID"] = str(pid)
                        log(f"   ✅ Successfully created place → ID: {pid}")
                    else:
                        log("   ✅ Success but failed to extract ID from JSON")
                except Exception:
                    df.at[index, "Status"] = "Success (JSON Parse Failed)"
                    df.at[index, "Response"] = resp.text
                    log("   ⚠️ Created but JSON parse failed")
            else:
                err_text = resp.text[:200]
                df.at[index, "Status"] = "Failed"
                df.at[index, "Failure Reason"] = f"HTTP {resp.status_code}: {err_text}"
                df.at[index, "Response"] = resp.text
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
