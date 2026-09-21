import os
import json
import sys
from app.standalone import Weekly_Report

def main():
    # Ensure outputs directory exists
    os.makedirs("outputs", exist_ok=True)
    output_path = os.path.join("outputs", "Weekly_Report_Output.xlsx")
    
    # Load configuration
    config_path = os.path.join("json_config", "weekly_report_config.json")
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found.")
        sys.exit(1)
        
    with open(config_path, "r") as f:
        config = json.load(f)
        
    # Callback to print logs to GitHub Actions console
    def log_callback(msg):
        print(msg)
        
    # Read action argument ('send' or 'fetch'), default to 'send'
    action = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].strip() else "send"
    print(f"Starting Weekly Report via GitHub Actions with action='{action}'...")
    
    try:
        # Run the report and trigger the specified action ('send' or 'fetch')
        Weekly_Report.run(None, output_path, config, log_callback=log_callback, action=action)
        print("Weekly Report executed successfully.")
    except Exception as e:
        print(f"Error executing report: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
