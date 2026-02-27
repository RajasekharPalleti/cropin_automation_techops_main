"""
Adds tags to entities in bulk using the Master API.

Inputs:
Excel file with Entity IDs and Tag Names.
"""
import pandas as pd
import requests

import time

def post_data_to_api(post_api_url, access_token_bearer, input_excel_file, output_excel_file, log_callback=None, delay_time=0.5):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    # Read the Excel file
    try:
        df = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"Failed to read input Excel file: {e}")
        return

    # Add a status column to track the response of each iteration
    df['Status'] = ''
    df['Response'] = ''  # Add a column to store the full response

    # Set up headers for the API request
    headers = {
        'Authorization': f'Bearer {access_token_bearer}',
        'Content-Type': 'application/json'
    }

    # Iterate through each row in the Excel file
    for index, row in df.iterrows():
        log(f"Processing iteration {index + 1}...")

        # Construct the payload from the row data
        try:
            payload = {
                  "name" : row.iloc[0],
                  "tagType" : row.iloc[1],
                  "validFrom" : row.iloc[2],
                  "validTill" : row.iloc[3],
                  "description" : row.iloc[4],
                  "status" : "Active",
            }
        except IndexError:
             df.at[index, 'Status'] = "Error"
             df.at[index, 'Response'] = "Row does not have enough columns"
             continue

        # Make the POST request
        try:
            log(f"Adding Tag {row.iloc[0]} to the API ...")
            response = requests.post(post_api_url, headers=headers, json=payload)
            # Record the status and full response of the request
            if response.status_code == 201:
                df.at[index, 'Status'] = 'Success'
                df.at[index, 'Response'] = f"Code: {response.status_code}, Message: {response.text}"
                log(f"Added Tag {row.iloc[0]} successfully to the API ...")
            else:
                df.at[index, 'Status'] = f"Failed: {response.status_code}"
                df.at[index, 'Response'] = f"Reason: {response.reason}, Message: {response.text}"
                log(f"Failed to add Tag {row.iloc[0]}: {response.status_code}")
        except Exception as e:
            df.at[index, 'Status'] = "Error"
            df.at[index, 'Response'] = str(e)
            log(f"Error processing {row.iloc[0]}: {e}")

        # Wait for 0.5 second before the next iteration
        time.sleep(delay_time)

    # Save the updated DataFrame with status to a new Excel file
    log("Saving updated DataFrame to a new Excel file...")
    try:
        df.to_excel(output_excel_file, index=False)
        log("File saved successfully.")
    except Exception as e:
        log(f"Error saving file: {e}")

def run(input_excel_file, output_excel_file, config, log_callback=None):
    """
    Executes the automation logic.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    api_url = config.get("post_api_url")
    # The token is injected into config by main.py after authentication
    token = config.get("token")
    
    if not api_url:
        raise ValueError("Configuration 'post_api_url' is missing.")
    
    if not token:
        log("Warning: No token found in config. Authentication might have failed or not run.")
        # We allow it to proceed potentially, or fail inside post_data_to_api
    
    delay_time = float(config.get("delay_time", 0.5))  # seconds, configurable via UI
    log(f"Starting execution with API: {api_url}")
    
    post_data_to_api(api_url, token, input_excel_file, output_excel_file, log_callback=log_callback, delay_time=delay_time)
