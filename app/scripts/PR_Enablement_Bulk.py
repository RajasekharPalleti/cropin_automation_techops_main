"""
Enables Plot Risk in bulk (batch mode) for multiple areas.

Inputs:
Excel file with croppable_area_id. Supports batch processing of 25, the sheet name should be "result" or it will pick the first sheet.
"""
import pandas as pd
import requests
import time
import json

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    # =========================
    # ACCESS TOKEN
    # =========================
    token = config.get("token")
    if not token:
        log("❌ Token missing. Exiting.")
        return
    log("✅ Access token loaded")

    # =========================
    # API CONFIG
    # =========================
    # Default to user provided partial URL if not in config, but fixing domain
    default_url = "https://cloud.cropin.in/services/farm/api/croppable-areas/plot-risk/batch"
    plot_risk_url = config.get("post_api_url")
    if not plot_risk_url:
        plot_risk_url = default_url
        log(f"Using default URL: {plot_risk_url}")
    else:
        log(f"Using configured URL: {plot_risk_url}")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # =========================
    # LOAD EXCEL
    # =========================
    log(f"📘 Loading Excel file: {input_excel_file}")
    try:
        # User requested sheet_name="result". Tying to use it, falling back to 0 if fails?
        # User requirement seemed specific. Let's try explicit first.
        try:
             df = pd.read_excel(input_excel_file, sheet_name="result")
        except:
             log("⚠️ Sheet 'result' not found. Loading first sheet.")
             df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    # =========================
    # ENSURE REQUIRED COLUMNS
    # =========================
    required_columns = [
        "status",
        "Failed in Response",
        "srPlotid",
        "Plot_risk_response"
    ]

    for col in required_columns:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str)

    BATCH_SIZE = 25

    # =========================
    # BATCH PROCESSING
    # =========================
    for start in range(0, len(df), BATCH_SIZE):
        time_delay = config.get("time_delay", 5)
        end = start + BATCH_SIZE
        batch_df = df.iloc[start:end]

        payload = []
        index_map = {}

        for index, row in batch_df.iterrows():
            # Try finding column by name first, else first column
            if "croppable_area_id" in df.columns:
                 croppable_area_id = str(row["croppable_area_id"]).strip()
            # fallback to camelCase if present
            elif "croppableAreaId" in df.columns:
                 croppable_area_id = str(row["croppableAreaId"]).strip()
            else:
                 croppable_area_id = str(row.iloc[0]).strip()
            
            # Handle NaN/Empty
            if not croppable_area_id or croppable_area_id.lower() == 'nan':
                continue

            # Determine Farmer ID based on config and excel
            farmer_id = None
            use_farmer_id_config = config.get("use_farmer_id", "no")

            if use_farmer_id_config == "yes":
                if 'farmer_id' in df.columns:
                    val = str(row['farmer_id']).strip()
                    if val and val.lower() != 'nan':
                        farmer_id = val
            
            payload.append({
                "croppableAreaId": croppable_area_id,
                "farmerId": farmer_id
            })
            index_map[croppable_area_id] = index

        if not payload:
            continue

        log(f"📡 Sending batch {start + 1} → {min(end, len(df))} (Size: {len(payload)})")

        try:
            response = requests.post(plot_risk_url, headers=headers, json=payload)
            response.raise_for_status()
            response_json = response.json()

            # Save full response for all rows in batch
            for idx in batch_df.index:
                df.at[idx, "Plot_risk_response"] = json.dumps(response_json)

            sr_plot_details = response_json.get("srPlotDetails", {})

            # Handle each returned CA
            for ca_id, details in sr_plot_details.items():
                row_idx = index_map.get(ca_id)
                if row_idx is None:
                    continue

                df.at[row_idx, "srPlotid"] = details.get("srPlotId", "N/A")

                if details.get("status") == "FAILED":
                    df.at[row_idx, "status"] = "❌ Failed"
                    df.at[row_idx, "Failed in Response"] = details.get("message", "Failed")
                else:
                    df.at[row_idx, "status"] = "✅ Success"
                    df.at[row_idx, "Failed in Response"] = "✅ Success"

            # Handle IDs not returned in response
            returned_ids = set(sr_plot_details.keys())
            for ca_id, idx in index_map.items():
                if ca_id not in returned_ids:
                    df.at[idx, "status"] = "❌ Failed"
                    df.at[idx, "Failed in Response"] = "No response from API"
                    df.at[idx, "srPlotid"] = "N/A"

            log("✅ Batch completed")

        except requests.exceptions.RequestException as e:
            log(f"❌ Batch failed: {e}")
            for idx in batch_df.index:
                df.at[idx, "status"] = "❌ Failed"
                df.at[idx, "Failed in Response"] = str(e)
                df.at[idx, "srPlotid"] = "N/A"
        
        # User script had specific sleep
        time.sleep(time_delay) 
        log(f"waiting for {time_delay} seconds") 

    # =========================
    # SAVE EXCEL
    # =========================
    log("💾 Writing results to Excel...")
    try:
        # Saving to the dedicated output file from the runner framework
        df.to_excel(output_excel_file, index=False)
        log(f"🎯 Done. Excel updated successfully at: {output_excel_file}")
    except Exception as e:
        log(f"❌ Error saving output: {e}")
