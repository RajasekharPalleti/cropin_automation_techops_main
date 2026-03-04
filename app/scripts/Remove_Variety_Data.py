"""
Script: Remove specific data from varieties (e.g., cropStages, seedGrades, subCompanyIds, harvestGrades and varietyAdditionalAttributes).

Inputs:
Excel file with 'VarietyID'. Config: fields_to_remove (list) example: ["cropStages", "seedGrades"].
"""
# Author: Rajasekhar Palleti
# Script: Remove specific data from varieties (e.g., cropStages, seedGrades)
# Inputs: Excel file with 'VarietyID'. Config: fields_to_remove (

import json
import requests
import pandas as pd
import time

def run(input_excel, output_excel, config_dict, log_callback=None):
    """
    Main execution function.
    """
    def log(message):
        if log_callback:
            log_callback(message)
        else:
            print(message)

    try:
        token = config.get("token")
        base_url = config.get("base_api_url", "https://cloud.cropin.in/services/farm/api/varieties")

        delay_time = float(config.get("delay_time", 0.5))  # seconds, configurable via UI

        # Get list of fields to clear
        fields_to_remove = config.get("fields_to_remove", [])
        
        if not fields_to_remove:
            log("⚠️ No fields selected for removal. Please configure fields in the UI.")
            return

        log(f"Starting process. URL: {base_url}")
        log(f"Fields to clear: {fields_to_remove}")

        df = pd.read_excel(input_excel)
        df['Status'] = ''
        df['Response'] = ''

        headers = {"Authorization": f"Bearer {token}"}
        
        # Ensure VarietyID column exists
        id_col = None
        for col in df.columns:
            if str(col).strip().lower() in ['varietyid', 'variety id', 'id']:
                id_col = col
                break
        
        if not id_col:
            # Fallback to first column
            id_col = df.columns[0]
            log(f"⚠️ 'VarietyID' column not explicitly found. Using first column: '{id_col}'")

        for i, row in df.iterrows():
            try:
                variety_id = row[id_col]
                if pd.isna(variety_id):
                    continue
                variety_id = int(variety_id)

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

                # --- Clear specified fields ---
                updated = False
                for field in fields_to_remove:
                    if field in variety_data:
                        if variety_data[field] == []:
                            # If this specific field is already empty, we don't need to do anything for IT.
                            # But we shouldn't skip the whole row yet, because OTHER fields might need clearing.
                            pass
                        else:
                            variety_data[field] = []
                            updated = True
                    else:
                        # If field is missing, we add it as empty list to ensure it is returned/cleared
                        variety_data[field] = []
                        updated = True

                if updated:
                    try:
                        update_response = requests.put(base_url, headers=headers, json=variety_data)
                        update_response.raise_for_status()
                        
                        df.at[i, 'Status'] = "Success"
                        df.at[i, 'Response'] = "Fields cleared successfully"
                        log(f"🚀 Variety ID {variety_id} updated. Cleared: {fields_to_remove}")
                    except Exception as update_err:
                        df.at[i, 'Status'] = "Failed"
                        df.at[i, 'Response'] = f"Update error: {update_err}"
                        log(f"❌ Failed to update variety {variety_id}: {update_err}")
                else:
                    df.at[i, 'Status'] = "Skipped"
                    df.at[i, 'Response'] = "No changes needed"
                    log(f"ℹ️ Variety ID {variety_id} skipped (no updates).")

            except Exception as e:
                df.at[i, 'Status'] = "Failed"
                df.at[i, 'Response'] = str(e)
                log(f"❌ Error processing row {i+2}: {e}")

            time.sleep(delay_time)

        # --- Save output ---
        df.to_excel(output_excel, index=False)
        log(f"✅ All processing complete. Output saved.")

    except Exception as e:
        log(f"Critical Error: {str(e)}")
        raise e
