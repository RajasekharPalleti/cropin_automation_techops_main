"""
Identify croppable areas outside India using their coordinates and delete their area audits.
Author: Rajasekhar Palleti

Inputs:
Excel file with 'croppable_area_id', 'latitude', and 'longitude'.
"""

import zipfile
from pathlib import Path
import time
import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import os
from tqdm import tqdm

# ================= CONFIG =================

DOWNLOADS_DIR = Path("ne_data")
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

NE_COUNTRIES_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_countries.zip"

_INDIA_GEOM = None  # cache


def _download_zip(url: str, zip_path: Path, extract_dir: Path, log_callback=None) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    if any(extract_dir.glob("*.shp")):
        return

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if log_callback:
        log_callback(f"Downloading {zip_path.name}...")
        
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        with open(zip_path, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=f"Downloading {zip_path.name}"
        ) as pbar:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))

    if log_callback:
        log_callback("Extracting naturalearth data...")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)


def _load_india_geom(log_callback=None):
    """Load India polygon geometry using Shapely 2.x union_all()."""
    global _INDIA_GEOM
    if _INDIA_GEOM is not None:
        return _INDIA_GEOM

    countries_zip = DOWNLOADS_DIR / "ne_50m_admin_0_countries.zip"
    countries_dir = DOWNLOADS_DIR / "ne_50m_admin_0_countries"
    _download_zip(NE_COUNTRIES_URL, countries_zip, countries_dir, log_callback)

    shp_files = list(countries_dir.glob("*.shp"))
    if not shp_files:
        raise RuntimeError("Admin 0 countries shapefile missing after download.")

    if log_callback:
        log_callback("Loading geopandas boundaries for geometry evaluation...")
        
    gdf = gpd.read_file(shp_files[0])
    gdf = gdf.set_crs("EPSG:4326") if gdf.crs is None else gdf.to_crs("EPSG:4326")

    for col in ("ADM0_A3", "ISO_A3", "GU_A3", "WB_A3", "SOVEREIGNT", "ADMIN", "NAME"):
        if col in gdf.columns:
            if col in ("ADM0_A3", "ISO_A3", "GU_A3", "WB_A3"):
                tmp = gdf[gdf[col].str.upper() == "IND"]
            else:
                tmp = gdf[gdf[col].str.contains("India", case=False, na=False)]
            if not tmp.empty:
                try:
                    _INDIA_GEOM = tmp.union_all()
                except AttributeError:
                    _INDIA_GEOM = tmp.unary_union
                return _INDIA_GEOM

    raise RuntimeError("India polygon not found in shapefile.")


def run(input_excel_file, output_excel_file, config, log_callback=None):
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)
            
    # 1. Parse Config
    base_api_url = config.get("base_api_url", "https://cloud.cropin.in/services/farm/api/croppable-areas")
    token = config.get("token")
    
    if not base_api_url:
        log("Error: API URL not configured.")
        return
    if not token:
        log("Error: Authorization token missing.")
        return
        
    delay_time = float(config.get("delay_time", 0.5))

    ca_id_column = "croppable_area_id"
    latitude_column = "latitude"
    longitude_column = "longitude"
    
    # Area Audit delete endpoint: "https://cloud.cropin.in/services/farm/api/croppable-areas/{ca_id}/area-audit"
    # base API is: https://cloud.cropin.in/services/farm/api/croppable-areas
    area_audit_delete_url = base_api_url.rstrip("/") + "/{ca_id}/area-audit"

    # read Excel
    log(f"📂 Reading input Excel: {input_excel_file}")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"Failed to read Excel: {e}")
        return

    # Column validation
    required_cols = [latitude_column, longitude_column, ca_id_column]
    for col in required_cols:
        if col not in df.columns:
            log(f"Error: Missing required column in excel: {col}")
            return

    df[latitude_column] = pd.to_numeric(df[latitude_column], errors="coerce")
    df[longitude_column] = pd.to_numeric(df[longitude_column], errors="coerce")

    # Add result columns and ensure string type to avoid TypeError
    df["is_outside_india"] = "INVALID"
    df["area_audit_status"] = ""
    df["area_audit_status"] = df["area_audit_status"].fillna("").astype(str)
    
    df["area_audit_api_response"] = ""
    df["area_audit_api_response"] = df["area_audit_api_response"].fillna("").astype(str)
    
    log("Loading India Polygon Geometry...")
    try:
        india_geom = _load_india_geom(log_callback)
    except Exception as e:
        log(f"Failed to load India boundary: {e}")
        return

    log("Geometry processing...")
    # Create spatial points
    geometries = [
        Point(lon, lat) if pd.notna(lat) and pd.notna(lon) else None
        for lat, lon in zip(df[latitude_column], df[longitude_column])
    ]

    gdf = gpd.GeoDataFrame(df, geometry=geometries, crs="EPSG:4326")
    valid_mask = gdf["geometry"].notna()

    log(f"Found {valid_mask.sum()} valid coordinate points out of {len(df)} total rows.")

    inside_mask = (
        gdf.loc[valid_mask, "geometry"].within(india_geom)
        | gdf.loc[valid_mask, "geometry"].touches(india_geom)
    )

    df.loc[valid_mask & inside_mask, "is_outside_india"] = "NO"
    df.loc[valid_mask & ~inside_mask, "is_outside_india"] = "YES"

    headers = {
        "Authorization": f"Bearer {token}"
    }

    log("Starting Area Audit removal logic...")
    processed_count = 0
    
    # Delete requests
    for index, row in df.iterrows():
        is_outside = row["is_outside_india"]
        ca_id = row[ca_id_column]
        
        ca_id_str = str(ca_id).strip() if pd.notna(ca_id) else "N/A"
        
        if is_outside != "YES":
            df.at[index, "area_audit_status"] = "SKIPPED"
            msg = "Inside India" if is_outside == "NO" else "Invalid coordinates"
            df.at[index, "area_audit_api_response"] = msg
            continue

        if pd.isna(ca_id) or ca_id_str == "" or ca_id_str == "nan":
            df.at[index, "area_audit_status"] = "FAILED"
            df.at[index, "area_audit_api_response"] = "Missing CA ID"
            log(f"Row {index+2}: FAILED - Missing CA ID")
            continue

        delete_url = area_audit_delete_url.format(ca_id=ca_id_str)
        
        try:
            response = requests.delete(delete_url, headers=headers, timeout=30)
            
            if response.status_code in (200, 204):
                df.at[index, "area_audit_status"] = "DELETED"
                df.at[index, "area_audit_api_response"] = "Success"
                log(f"Row {index+2}: CA {ca_id_str} Area Audit Status: DELETED")
            else:
                df.at[index, "area_audit_status"] = "FAILED"
                df.at[index, "area_audit_api_response"] = response.text
                log(f"Row {index+2}: CA {ca_id_str} Failure: {response.text}")

        except requests.RequestException as e:
            df.at[index, "area_audit_status"] = "FAILED"
            df.at[index, "area_audit_api_response"] = str(e)
            log(f"Row {index+2}: CA {ca_id_str} Exception: {e}")

        processed_count += 1
        time.sleep(delay_time)

    # Clean up geopandas geometry field before output saving
    if "geometry" in df.columns:
        df = df.drop(columns=["geometry"])

    # Save output
    log(f"💾 Saving outputs off to Excel log...")
    try:
        df.to_excel(output_excel_file, index=False)
        log("✅ Processing completed successfully")
    except Exception as e:
         log(f"Failed to save output Excel file: {e}")
