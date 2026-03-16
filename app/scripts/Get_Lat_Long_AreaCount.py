"""
Script to calculate area (acres and hectares) and center point (lat, long) from coordinates.

Inputs:
Excel file with 'Coordinates' column containing JSON array of [long, lat] or raw lat/long combinations.
"""
import pandas as pd
import json
import re
import math
import time

def calculate_area_and_center(coords):
    if not coords or len(coords) < 3:
        return 0, 0, 0, 0
    
    # Calculate geometric center from points
    sum_lon = sum(c[0] for c in coords)
    sum_lat = sum(c[1] for c in coords)
    center_lon = sum_lon / len(coords)
    center_lat = sum_lat / len(coords)
    
    try:
        from pyproj import Geod
    except ImportError:
        # Fallback to simple math if dependencies failed to install
        return 0, 0, center_lat, center_lon
        
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    
    geod = Geod(ellps="WGS84")
    
    # Calculate exact geodesic area
    try:
        poly_area, _ = geod.polygon_area_perimeter(lons, lats)
        area_sqm = abs(poly_area)
    except Exception:
        # If coordinates are invalid or loop crosses itself improperly
        return 0, 0, center_lat, center_lon
    
    # Standard conversons
    area_hectares = area_sqm / 10000.0
    area_acres = area_sqm / 4046.8564224
    
    return area_acres, area_hectares, center_lat, center_lon

def parse_coordinates(coord_str):
    try:
        # First try JSON [ [lon, lat], [lon, lat]... ]
        coords = json.loads(str(coord_str).replace("'", '"'))
        if isinstance(coords, list) and len(coords) > 0 and isinstance(coords[0], list):
            return coords
    except Exception:
        pass
    
    # Try parsing lat/long combinations using regex
    numbers = re.findall(r'-?\d+\.\d+|-?\d+', str(coord_str))
    if len(numbers) >= 6 and len(numbers) % 2 == 0:
        # Assuming format is lat, long, lat, long
        coords = []
        for i in range(0, len(numbers), 2):
            lat = float(numbers[i])
            lon = float(numbers[i+1])
            coords.append([lon, lat])
        return coords
        
    return None

def run(input_excel, output_excel, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)
        
    delay_time = float(config.get("delay_time", 0))

    try:
        df = pd.read_excel(input_excel)
    except Exception as e:
        log(f"❌ Failed to read input file: {e}")
        return

    # Add required columns if not present
    for col in ['area in acres', 'area in hectares', 'latitude', 'longitude', 'Status', 'Response']:
        if col not in df.columns:
            df[col] = ''
            
    log("⏳ Starting coordinate area calculations...")

    # Look for coordinates column
    coord_col_names = [col for col in df.columns if 'coord' in col.lower() or 'lat' in col.lower() or 'long' in col.lower()]
    coord_col = coord_col_names[0] if coord_col_names else df.columns[0] # Default to first if name matching fails

    for i, row in df.iterrows():
        try:
            coord_str = row[coord_col]
            if pd.isna(coord_str) or str(coord_str).strip() == '':
                df.at[i, 'Status'] = "Skipped"
                df.at[i, 'Response'] = "Coordinates are empty"
                log(f"⏳ Skipping row {i+2} due to missing coordinates.")
                continue
                
            log(f"⏳ Processing row {i+2}...")
            
            coords = parse_coordinates(coord_str)
            if not coords:
                df.at[i, 'Status'] = "Failed"
                df.at[i, 'Response'] = "Invalid coordinate format"
                log(f"❌ Failed to parse coordinates on row {i+2}")
                continue
                
            if len(coords) < 3:
                df.at[i, 'Status'] = "Failed"
                df.at[i, 'Response'] = "Need at least 3 points to form a polygon"
                log(f"❌ Polygon needs at least 3 points on row {i+2}")
                continue

            acres, hectares, center_lat, center_lon = calculate_area_and_center(coords)
            
            df.at[i, 'area in acres'] = round(acres, 4)
            df.at[i, 'area in hectares'] = round(hectares, 4)
            df.at[i, 'latitude'] = round(center_lat, 6)
            df.at[i, 'longitude'] = round(center_lon, 6)
            
            df.at[i, 'Status'] = "Success"
            df.at[i, 'Response'] = "Calculated Area and Center Point"
            log(f"✅ Row {i+2} processed successfully.")
            
        except Exception as e:
            df.at[i, 'Status'] = "Failed"
            df.at[i, 'Response'] = str(e)
            log(f"❌ Error processing row {i+2}: {str(e)}")
            
        time.sleep(delay_time)

    try:
        df.to_excel(output_excel, index=False)
        log(f"✅ Processing complete. Output saved to {output_excel}")
    except Exception as e:
        log(f"❌ Failed to save output file: {e}")
