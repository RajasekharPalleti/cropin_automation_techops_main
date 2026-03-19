"""
Bulk delete assets using Excel input (Default 100 IDs per batch will execute).

Inputs:
- Excel file with 'asset_id' column.
- One ID per row in the 'asset_id' column.
"""
import pandas as pd
import requests
import time

def run(input_excel_file, output_excel_file, config, log_callback=None):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)


    # Configuration
    token = config.get("token")
    if not token:
        log("❌ No token provided in configuration.")
        return

    api_url = config.get("base_api_url")
    if not api_url:
        api_url = "https://cloud.cropin.in/services/farm/api/assets/bulk"
        log(f"Using default API URL: {api_url}")
    api_url = api_url.rstrip('/')

    BATCH_SIZE = int(config.get("bulk_batch_size", config.get("batch_size", 100)))
    delay_time = float(config.get("delay_time", 2))
    
    log(f"📘 Loading Excel file: {input_excel_file}")

    try:
        # Load Excel
        df = pd.read_excel(input_excel_file)
        
        if "asset_id" not in df.columns:
            # Try case-insensitive matching
            possible = [c for c in df.columns if c.lower().strip() == "asset_id"]
            if possible:
                df.rename(columns={possible[0]: "asset_id"}, inplace=True)
            else:
                 log("❌ Excel must contain 'asset_id' column")
                 return

        # Ensure asset_id is string type immediately to avoid formatting errors
        df["asset_id"] = df["asset_id"].astype(str).str.replace(r'\.0$', '', regex=True)

        # Ensure tracking columns
        for col in ["Status", "Processed_IDs", "API_Response"]:
            if col not in df.columns:
                df[col] = ""
            # Explicitly cast to string after filling NaNs to prevent TypeError in newer pandas versions
            df[col] = df[col].fillna("").astype(str)

        # Clean IDs
        df_clean = df.dropna(subset=["asset_id"])
        
        # Identify rows that have asset_id
        valid_indices = df[df["asset_id"].notna() & (df["asset_id"].astype(str).str.strip() != "")].index.tolist()
        
        asset_ids = df.loc[valid_indices, "asset_id"].astype(str).tolist()

        total_rows = len(asset_ids)
        processed_count = 0
        log(f"🚀 Total Assets to Delete: {total_rows}")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        for i in range(0, len(asset_ids), BATCH_SIZE):
            batch_slice_ids = asset_ids[i:i + BATCH_SIZE]
            batch_indices = valid_indices[i:i + BATCH_SIZE]
            
            ids_param = ",".join(batch_slice_ids)
            pending_rows = total_rows - processed_count

            log(f"\n🗑️ Deleting batch {i // BATCH_SIZE + 1} | Items: {len(batch_slice_ids)} | Processed: {processed_count} | Pending: {pending_rows}")

            try:
                response = requests.delete(
                    api_url,
                    headers=headers,
                    params={"ids": ids_param},
                    timeout=60
                )

                status_code = response.status_code
                response_text = response.text

                if status_code in [200, 204]:
                    status = "✅ Deleted"
                    log(f"✅ Batch {i // BATCH_SIZE + 1} deleted successfully")
                else:
                    status = f"❌ Failed ({status_code})"
                    log(f"❌ Batch {i // BATCH_SIZE + 1} delete failed: {status_code}")

            except Exception as e:
                status = "❌ Error"
                response_text = str(e)
                log(f"❌ Exception occurred in batch {i // BATCH_SIZE + 1}: {e}")

            # Update rows for this batch
            df.loc[batch_indices, "Status"] = status
            df.loc[batch_indices[0], "Processed_IDs"] = ids_param
            df.loc[batch_indices[0], "API_Response"] = response_text

            processed_count += len(batch_slice_ids)

            # Live save to output
            df.to_excel(output_excel_file, index=False)
            time.sleep(delay_time)

        log(f"\n🎯 Process completed. Output saved to: {output_excel_file}")

    except Exception as e:
        log(f"❌ Critical Error: {e}")
        import traceback
        traceback.print_exc()
