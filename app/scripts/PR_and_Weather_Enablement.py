"""
Enables both Plot Risk and Weather services for croppable areas.

Inputs:
Excel file with croppable_area_id and optionally farmer_id.
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

    # Configuration
    token = config.get("token")
    base_url = config.get("post_api_url")
    
    if not token:
        log("❌ Failed to retrieve access token. Process terminated.")
        return

    if not base_url:
        base_url = "https://cloud.cropin.in/services/farm/api/croppable-areas"
        log(f"No API URL provided, using default base: {base_url}")
    
    base_url = base_url.rstrip('/')
    
    plot_risk_url = f"{base_url}/plot-risk/batch"
    sustainability_url = f"{base_url}/sustainability/batch?features=WEATHER"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    delay_time = float(config.get("delay_time", 2))  # seconds, configurable via UI

    log("Reading Excel file...")
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"Error reading Excel file: {e}")
        return

    # Ensure necessary columns exist
    columns_to_check = ["status", "Failed in Response", "srPlotid", "Plot_risk_response", "Weather_response"]
    for col in columns_to_check:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str)

    # Function to extract srPlotId
    def extract_sr_plot_id(response_json):
        if "srPlotDetails" in response_json:
            for details in response_json["srPlotDetails"].values():
                return details.get("srPlotId")

        for key, value in response_json.items():
            if isinstance(value, list):
                for item in value:
                    if "srPlotId" in item:
                        return item["srPlotId"]
        return "N/A"

    # Iterate over rows
    for index, row in df.iterrows():
        try:
            # Flexible reading for croppable_area_id
            if 'croppable_area_id' in df.columns:
                 croppable_area_id = str(row['croppable_area_id']).strip()
            else:
                 croppable_area_id = str(row.iloc[0]).strip()
            
            if not croppable_area_id or croppable_area_id.lower() == 'nan':
                 log(f"Skipping empty row {index + 1}")
                 continue

            # Determine Farmer ID based on config and excel
            farmer_id = None
            use_farmer_id_config = config.get("use_farmer_id", "no")
            
            if use_farmer_id_config == "yes":
                if 'farmer_id' in df.columns:
                    val = str(row['farmer_id']).strip()
                    if val and val.lower() != 'nan':
                        farmer_id = val
            
            log(f"🔄 Processing row {index + 1}: CroppableAreaId = {croppable_area_id}, FarmerId = {farmer_id}")

            # Construct payloads
            plot_risk_payload = [{"croppableAreaId": croppable_area_id, "farmerId": farmer_id}]
            sustainability_payload = [croppable_area_id]

            # 1. Send Plot Risk API request
            log(f"📡 Sending Plot Risk API request for CroppableAreaId: {croppable_area_id}")
            plot_risk_response = None
            plot_risk_json = {}
            try:
                plot_risk_response = requests.post(plot_risk_url, json=plot_risk_payload, headers=headers)
                plot_risk_response.raise_for_status()
                plot_risk_json = plot_risk_response.json()
                
                df.at[index, "Plot_risk_response"] = json.dumps(plot_risk_json)
                df.at[index, "srPlotid"] = extract_sr_plot_id(plot_risk_json)
                log(f"✅ Extracted srPlotId: {df.at[index, 'srPlotid']}")
            except requests.exceptions.RequestException as req_err:
                error_message = str(req_err)
                df.at[index, "Plot_risk_response"] = error_message
                df.at[index, "srPlotid"] = "N/A"
                log(f"❌ Plot Risk API request failed: {error_message}")
                # We define plot_risk_response as mock object with status code 0 if failed, to handle check later
                class MockResponse:
                    status_code = 0
                if plot_risk_response is None: plot_risk_response = MockResponse()

            time.sleep(delay_time)

            # 2. Send Weather API request
            log(f"📡 Sending Weather API request for CroppableAreaId: {croppable_area_id}")
            sustainability_response = None
            try:
                sustainability_response = requests.post(sustainability_url, json=sustainability_payload, headers=headers)
                sustainability_response.raise_for_status()
                sustainability_json = sustainability_response.json()
                df.at[index, "Weather_response"] = json.dumps(sustainability_json)
            except requests.exceptions.RequestException as req_err:
                error_message = str(req_err)
                df.at[index, "Weather_response"] = error_message
                log(f"❌ Weather API request failed: {error_message}")
                class MockResponse:
                    status_code = 0
                if sustainability_response is None: sustainability_response = MockResponse()

            # Update status column based on BOTH calls
            if (plot_risk_response.status_code == 200 and sustainability_response.status_code == 200):
                df.at[index, "status"] = "✅ Success"
            else:
                df.at[index, "status"] = "❌ Failed"

            # Check if Failed in response of plotrisk API
            sr_plot_details = plot_risk_json.get("srPlotDetails", {})
            failed_found = False
            for key, value in sr_plot_details.items():
                if value.get("status") == "FAILED":
                    failed_found = True
                    msg = value.get('message', 'No message provided')
                    log(f"❌ Status for {key}: {value['status']} - {msg}")
                    df.at[index, "Failed in Response"] = f"❌ Failed: {msg}"
            
            if not failed_found:
                df.at[index, "Failed in Response"] = "✅ Success"

        except Exception as e:
            error_message = str(e)
            df.at[index, "status"] = f"⚠️ Error: {error_message}"
            log(f"⚠️ Error in row {index + 1}: {error_message}")

        time.sleep(delay_time)

    # Save output
    log("🎯 Processing completed. Saving output file...")
    try:
        df.to_excel(output_excel_file, index=False)
        log("File saved successfully.")
    except Exception as e:
        log(f"Error saving file: {e}")
