# Author: Rajasekhar Palleti
# QA Automation Script to Fetch Plan Type and Submit Plan Details via API (Refactored)

"""
Edits existing plans for crop varieties, supporting recurring schedules.

Inputs:
Excel file with plan_id, plan_name, plantype_id, schedule_type, no_of_days, execute_when, reference_date, required_days, and recurring details.
"""
import json
import pandas as pd
import requests
import time

# --- Utility functions ---
def safe_int(value):
    """Convert value to int safely"""
    try:
        if pd.isna(value) or value == "":
            return 0
        return int(float(value)) # Handle float strings like '1.0'
    except (ValueError, TypeError):
        return 0

def safe_bool(value):
    """Convert Excel values to boolean"""
    if str(value).strip().lower() in ["true", "1", "yes", "y"]:
        return True
    return False

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    # =========================
    # CONFIGURATION
    # =========================
    token = config.get("token")
    if not token:
        log("❌ Token missing. Exiting.")
        return
    
    # Use configured URL or default
    api_url = config.get("base_api_url")
    delay_time = float(config.get("delay_time", 0.3))  # seconds, configurable via UI
    if not api_url:
        api_url = "https://cloud.cropin.in/services/farm/api/plans"
        log(f"Using default API URL: {api_url}")
    else:
        log(f"Using configured API URL: {api_url}")

    log(f"\n[INFO] Loading data from Excel: {input_excel_file}")
    try:
        exdata = pd.read_excel(input_excel_file)
    except Exception as e:
        log(f"❌ Error reading Excel file: {e}")
        return

    log("[INFO] Cleaning data: Replacing NaN values with empty strings")
    exdata = exdata.fillna("")

    log("[INFO] Adding status tracking columns")
    exdata['status'] = ""
    exdata['Response'] = ''

    log(f"\n[INFO] Starting to process {len(exdata)} rows from the Excel file")

    headers = {"Authorization": f"Bearer {token}"}

    for index, row in exdata.iterrows():
        log(f"\n[ROW {index + 1}] Processing row")

        try:
            # --- Extract fields from Excel ---
            plan_id = str(row.get("plan_id", "")).strip()
            
            if not plan_id:
                log(f"[ROW {index + 1}] ⚠️ Skipped: Missing plan_id")
                continue

            plan_name = row.get("plan_name", "")
            plantype_id = row.get("plantype_id", "")
            schedule_type = row.get("schedule_type", "")
            no_of_days = safe_int(row.get("no_of_days", 0))
            execute_when = row.get("execute_when", "")
            reference_date = row.get("reference_date", "")
            required_days = safe_int(row.get("required_days", 0))
            recuring = safe_bool(row.get("recuring", False))
            repeat_after = safe_int(row.get("repeat_after", 0))
            timePeriod = row.get("timePeriod", "")
            hasRecuringEndDate = safe_bool(row.get("hasRecuringEndDate", False))
            recuringEndDate = row.get("recuringEndDate", "")
            recNoOfDays = safe_int(row.get("recNoOfDays", 0))
            recExecuteWhen = row.get("recExecuteWhen", "")
            recReferenceDate = row.get("recReferenceDate", "")

            # --- GET existing plan ---
            get_url = f"{api_url}/{plan_id}"
            log(f"[ROW {index + 1}] Sending GET request: {get_url}")

            get_response = requests.get(get_url, headers=headers)

            if get_response.status_code == 200:
                try:
                    plan_response = get_response.json()
                except ValueError:
                    log(f"[ROW {index + 1}] ❌ Invalid JSON in GET response")
                    exdata.at[index, 'status'] = "Invalid JSON"
                    continue
                log(f"[ROW {index + 1}] GET request successful")
            else:
                log(f"[ROW {index + 1}] ❌ GET failed with status: {get_response.status_code}")
                exdata.at[index, 'status'] = f"Failed GET: {get_response.status_code}"
                continue

            # Ensure schedule key exists
            if "schedule" not in plan_response:
                plan_response["schedule"] = {}

            # --- Conditional update ---
            if recuring:  # ✅ Update recurring schedule fields
                log(f"[ROW {index + 1}] Updating recurring schedule fields")
                plan_response["name"] = plan_name
                if "data" in plan_response and "information" in plan_response["data"]:
                    plan_response["data"]["information"]["planName"] = plan_name

                plan_response["schedule"]["type"] = schedule_type
                plan_response["schedule"]["noOfDays"] = no_of_days
                plan_response["schedule"]["executeWhen"] = execute_when
                plan_response["schedule"]["requiredDays"] = required_days
                plan_response["schedule"]["recuring"] = recuring
                plan_response["schedule"]["repeats"] = repeat_after
                plan_response["schedule"]["timePeriod"] = timePeriod
                plan_response["schedule"]["hasRecuringEndDate"] = hasRecuringEndDate
                plan_response["schedule"]["recuringEndDate"] = recuringEndDate
                plan_response["schedule"]["recNoOfDays"] = recNoOfDays
                plan_response["schedule"]["recExecuteWhen"] = recExecuteWhen

                # Handle referenceDate carefully
                if isinstance(reference_date, int) or str(reference_date).isdigit():
                    ref_val = int(reference_date)
                    plan_response["schedule"]["referenceDate"] = ref_val
                    plan_response["schedule"]["referencePlanId"] = ref_val
                else:
                    plan_response["schedule"]["referenceDate"] = reference_date

                # Handle recReferenceDate carefully
                if isinstance(recReferenceDate, int) or str(recReferenceDate).isdigit():
                    rec_ref_val = int(recReferenceDate)
                    plan_response["schedule"]["recReferenceDate"] = rec_ref_val
                else:
                    plan_response["schedule"]["recReferenceDate"] = recReferenceDate

            else:  # Update non-recurring schedule fields
                log(f"[ROW {index + 1}] Updating standard schedule fields")
                plan_response["name"] = plan_name
                if "data" in plan_response and "information" in plan_response["data"]:
                    plan_response["data"]["information"]["planName"] = plan_name

                plan_response["schedule"]["type"] = schedule_type
                plan_response["schedule"]["noOfDays"] = no_of_days
                plan_response["schedule"]["executeWhen"] = execute_when
                plan_response["schedule"]["requiredDays"] = required_days

                # Handle referenceDate carefully
                if isinstance(reference_date, int) or str(reference_date).isdigit():
                    ref_val = int(reference_date)
                    plan_response["schedule"]["referenceDate"] = ref_val
                    plan_response["schedule"]["referencePlanId"] = ref_val
                else:
                    plan_response["schedule"]["referenceDate"] = reference_date

            # --- PUT request to update ---
            multipart_data = {
                "dto": (None, json.dumps(plan_response), "application/json")
            }

            # Original script used put_url = f"{api_url}" (base URL) for PUT? 
            # Usually update is PUT /plans/{id} or PUT /plans with body containing ID
            # In Update_Farmer_Address.py we used base URL for multipart.
            # The logic in provided script was: put_url = f"{api_url}"
            # Let's stick to that as it matches the "Project Behaviour" request.
            put_url = api_url
            log(f"[ROW {index + 1}] Sending PUT request: {put_url}")

            put_response = requests.put(
                put_url,
                headers=headers,
                files=multipart_data
            )

            if put_response.status_code in [200, 201]:
                log(f"[ROW {index + 1}] ✅ PUT successful")
                exdata.at[index, 'status'] = "Success"
                exdata.at[index, 'Response'] = f"Code: {put_response.status_code}, Message: {put_response.text}"
            else:
                log(f"[ROW {index + 1}] ❌ PUT failed, Status: {put_response.status_code}")
                exdata.at[index, 'status'] = f"Failed PUT: {put_response.status_code}"
                exdata.at[index, 'Response'] = f"Reason: {put_response.reason}, Message: {put_response.text}"

            time.sleep(delay_time)  # Throttle API calls

        except Exception as e:
            log(f"[ROW {index + 1}] ❌ Error: {str(e)}")
            exdata.at[index, 'status'] = f"Error: {str(e)}"

    log(f"\n[INFO] Saving results to output Excel: {output_excel_file}")
    try:
        exdata.to_excel(output_excel_file, index=False)
        log("[INFO] Process completed successfully ✅")
    except Exception as e:
        log(f"❌ Error saving output file: {e}")
