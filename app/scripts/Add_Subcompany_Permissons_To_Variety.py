"""
Script: Add sub company permission to existing varieties based on Excel input.

Inputs:
Excel file with 'VarietyID', 'Variety Name', 'SubCompanyID' columns.
"""
# Author: Rajasekhar Palleti
# Script: Add sub company permission to existing varieties based on Excel input
# Inputs: Excel file with 'VarietyID', 'Variety Name', 'SubCompanyID' columns.

import json
import requests
import pandas as pd
import time
from datetime import datetime

def update_variety(token, variety_data, url):
    """Update variety with new data"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    response = requests.put(url, headers=headers, json=variety_data)
    response.raise_for_status()
    return response.json()

def run(input_excel, output_excel, config_dict, log_callback=None):
    """
    Main execution function called by the application.
    """
    def log(message):
        if log_callback:
            log_callback(message)
        else:
            print(message)

    try:
        token = config_dict.get("token")
        base_url = config_dict.get("url", "https://cloud.cropin.in/services/farm/api/varieties")
        
        # Get delay time from config, default to 1 seconds if not provided or invalid
        try:
            delay_time = float(config_dict.get("delay_time", 1))
        except (ValueError, TypeError):
            delay_time = 1
            
        log(f"Starting process with URL: {base_url} and Delay: {delay_time}s")

        df = pd.read_excel(input_excel)
        df['Status'] = ''
        df['Response'] = ''

        headers = {"Authorization": f"Bearer {token}"}

        for i, row in df.iterrows():
            try:
                variety_id = int(row['VarietyID'])
                
                # Parse SubCompany IDs (handle int or comma-separated string)
                sub_company_ids_to_add = []
                raw_sub_val = row['SubCompanyID']
                
                if isinstance(raw_sub_val, (int, float)) and not pd.isna(raw_sub_val):
                    sub_company_ids_to_add.append(int(raw_sub_val))
                elif isinstance(raw_sub_val, str):
                    for part in raw_sub_val.split(','):
                        if part.strip().isdigit():
                            sub_company_ids_to_add.append(int(part.strip()))
                            
                if not sub_company_ids_to_add:
                    df.at[i, 'Status'] = "Skipped"
                    df.at[i, 'Response'] = "No valid SubCompanyID found"
                    log(f"⚠️ Row {i+2}: No valid SubCompanyID found for Variety {variety_id}")
                    continue

                # --- Fetch variety data ---
                try:
                    variety_url = f"{base_url}/{variety_id}"
                    variety_response = requests.get(variety_url, headers=headers)
                    variety_response.raise_for_status()
                    variety_data = variety_response.json()
                except Exception as fetch_err:
                    df.at[i, 'Status'] = "Failed"
                    df.at[i, 'Response'] = f"Fetch error: {fetch_err}"
                    log(f"❌ Failed to fetch variety {variety_id}: {fetch_err}")
                    continue

                # --- Ensure subCompanyIds field is present ---
                if "subCompanyIds" not in variety_data or not isinstance(variety_data["subCompanyIds"], list):
                    variety_data["subCompanyIds"] = []

                # --- Add new SubCompany IDs if not already present ---
                ids_added = []
                for subCompany_id in sub_company_ids_to_add:
                    if subCompany_id not in variety_data["subCompanyIds"]:
                        variety_data["subCompanyIds"].append(subCompany_id)
                        ids_added.append(str(subCompany_id))

                if ids_added:
                    try:
                        update_response = update_variety(token, variety_data, base_url)
                        df.at[i, 'Status'] = "Success"
                        df.at[i, 'Response'] = json.dumps(update_response)
                        log(f"🚀 Variety ID {variety_id} updated with SubCompanies: {', '.join(ids_added)}")
                    except Exception as update_err:
                        df.at[i, 'Status'] = "Failed"
                        df.at[i, 'Response'] = f"Update error: {update_err}"
                        log(f"❌ Failed to update variety {variety_id}: {update_err}")
                else:
                    df.at[i, 'Status'] = "Skipped"
                    df.at[i, 'Response'] = "All SubCompany IDs already exist"
                    log(f"ℹ️ Variety ID {variety_id} already has SubCompanies {sub_company_ids_to_add}, skipped.")

            except Exception as e:
                df.at[i, 'Status'] = "Failed"
                df.at[i, 'Response'] = str(e)
                log(f"❌ Error processing row {i+2}: {e}")

            time.sleep(delay_time)  # prevent hitting API too fast

        # --- Save output ---
        df.to_excel(output_excel, index=False)
        log(f"✅ All processing complete. Output saved.")

    except Exception as e:
        log(f"Critical Error: {str(e)}")
        # Create an empty error file if possible or re-raise
        raise e
