# ──────────────────────────────────────────────────────────────────────────────
# Application-level configuration
# ──────────────────────────────────────────────────────────────────────────────

# Directory paths
SCRIPTS_DIR = "app/scripts"   # Location of automation scripts
UPLOAD_DIR  = "uploads"       # Temporary upload staging area
OUTPUT_DIR  = "outputs"       # Generated output files
TEMPLATES_DIR = "sample_templates"  # Excel template files

# Server settings
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 4444

# Proxy settings (for Google Drive API in corporate networks)
# Set these if you get WinError 10060 (Timeout) errors.
# Example: "http://proxy.cropin.in:8080"
HTTP_PROXY  = ""
HTTPS_PROXY = ""

# SSE / streaming settings
SSE_HEARTBEAT_TIMEOUT = 15.0  # seconds — keeps TCP connection alive when idle

# Backup cleanup settings
CLEANUP_RETENTION_DAYS    = 90     # Files older than this are deleted from Drive
CLEANUP_INTERVAL_SECONDS  = 86400  # Run cleanup once per day (24 h)


# ──────────────────────────────────────────────────────────────────────────────
# Script-specific API configurations for the /api/scripts endpoint.
# Each key is the Python script filename and the value defines the URL(s),
# label(s), and input requirements shown in the UI when that script is selected.

SCRIPT_CONFIGS = {
    "Add_Tags_With_New_API.py": {
        "base_api_url": "https://cloud.cropin.in/services/master/api/tags",
        "label": "Post Api Url",
        "requires_input": True,
    },
    "Update_Farmer_Details.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/farmers",
        "label": "Base Api Url",
        "requires_input": True,
        "show_attribute_config": True,
    },
    "Update_Farmer_Number_Data.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/farmers",
        "label": "Base Api Url",
        "requires_input": True,
        "show_attribute_config": True,
    },
    "Update_Asset_Details.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/assets",
        "label": "Base Api Url",
        "requires_input": True,
        "show_attribute_config": True,
    },
    "PR_Enablement.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
        "label": "Base Api Url",
        "requires_input": True,
        "show_pr_weather": True,
    },
    "PR_and_Weather_Enablement.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
        "label": "Base Api Url",
        "requires_input": True,
        "show_pr_weather": True,
    },
    "Refresh_Plans.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
        "label": "Base Api Url",
        "requires_input": True,
    },
    "Update_Asset_Additional_Attribute.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/assets",
        "label": "Base Api Url",
        "requires_input": True,
        "show_attribute_config": True,
    },
    "Update_Farmer_Additional_Attribute.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/farmers",
        "label": "Base Api Url",
        "requires_input": True,
        "show_attribute_config": True,
    },
    "Add_Users.py": {
        "base_api_url": "https://cloud.cropin.in/services/user/api/users/images",
        "label": "User API Url",
        "requires_input": True,
        "show_google_api_config": True,
    },
    "Area_Audit_Removal.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
        "label": "Base Api Url",
        "requires_input": True,
    },
    "Update_Farmer_Tags.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/farmers",
        "label": "Base Api Url",
        "requires_input": True,
        "show_threading": True,
    },
    "Update_Asset_Tags.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/assets",
        "label": "Base Api Url",
        "requires_input": True,
        "show_threading": True,
    },
    "Update_CA_Tags.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
        "label": "Base Api Url",
        "requires_input": True,
        "show_threading": True,
    },
    "Update_Farmer_Address.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/farmers",
        "label": "Base Api Url",
        "requires_input": True,
        "show_address_config": True,
    },
    "Update_Asset_Address.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/assets",
        "label": "Base Api Url",
        "requires_input": True,
        "show_address_config": True,
    },
    "PR_Enablement_Bulk.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas/plot-risk/batch",
        "label": "Base Api Url",
        "requires_input": True,
        "show_pr_weather": True,
        "show_batch_config": True,
    },
    "Edit_Plans_in_Variety_with_or_without_recurring.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/plans",
        "label": "Plan API URL",
        "requires_input": True,
    },
    "Area_Audit_To_CA.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
        "label": "Croppable Area API URL",
        "requires_input": True,
        "show_area_audit": True,
    },
    "Add_Cropstages_to_Variety.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/varieties",
        "label": "Variety API URL",
        "second_base_api_url": "https://cloud.cropin.in/services/farm/api/crop-stages",
        "label2": "Crop Stage API URL",
        "requires_input": True,
    },
    "Add_Seed_Grades_to_Variety.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/varieties",
        "label": "Variety API URL",
        "second_base_api_url": "https://cloud.cropin.in/services/farm/api/seed-grades",
        "label2": "Seed Grade API URL",
        "requires_input": True,
    },
    "Add_Varieties_or_Sub_Varieties.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/varieties",
        "label": "Variety API URL",
        "requires_input": True,
    },
    "Split_CAs.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/projects",
        "label": "Base API URL",
        "requires_input": True,
    },
    "Enable_Cropin_Connect.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/acresquare/farmers-enable",
        "label": "Enablement API URL",
        "requires_input": True,
    },
    "Delete_Users.py": {
        "base_api_url": "https://cloud.cropin.in/services/user/api/users/bulk",
        "label": "Delete API URL",
        "requires_input": True,
    },
    "Enable_Or_Disable_User.py": {
        "base_api_url": "https://cloud.cropin.in/services/user/api/users",
        "label": "Base Api Url",
        "requires_input": True,
    },
    "Bulk_Delete_Farmers.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/farmers/bulk",
        "label": "Base Api Url",
        "requires_input": True,
        "show_batch_config": True,
    },
    "Bulk_Delete_Assets.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/assets/bulk",
        "label": "Base Api Url",
        "requires_input": True,
        "show_batch_config": True,
    },
    "Update_DOS_Variety_to_CA.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
        "label": "Base Api Url",
        "requires_input": True,
    },
    "Update_DOS_to_CA.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
        "label": "Base Api Url",
        "requires_input": True,
    },
    "Update_Variety_to_CA.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
        "label": "Base Api Url",
        "requires_input": True,
    },
    "Farmer_Refresh_Edit_and_Save.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/farmers",
        "label": "Base Api Url",
        "requires_input": True,
    },
    "Asset_Refresh_Edit_and_Save.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/assets",
        "label": "Base Api Url",
        "requires_input": True,
    },
    "Delete_Farmer_Tags.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/farmers",
        "label": "Base Api Url",
        "second_base_api_url": "https://cloud.cropin.in/services/master/api/filter?type=FARMER&size=10000",
        "label2": "Tag Filter API Url",
        "requires_input": True,
    },
    "Delete_CA_Tags.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
        "label": "Base Api Url",
        "second_base_api_url": "https://cloud.cropin.in/services/master/api/filter?type=CA&size=10000",
        "label2": "Tag Filter API Url",
        "requires_input": True,
    },
    "Delete_Asset_Tags.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/assets",
        "label": "Base Api Url",
        "second_base_api_url": "https://cloud.cropin.in/services/master/api/filter?type=ASSET&size=10000",
        "label2": "Tag Filter API Url",
        "requires_input": True,
    },
    "Add_Geotag_or_Update_Lat_Long_to_CA.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
        "label": "Base Api Url",
        "requires_input": True,
    },
    "Add_Subcompany_Permissons_To_Variety.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/varieties",
        "label": "Variety API URL",
        "requires_input": True,
    },
    "Remove_Variety_Data.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/varieties",
        "label": "Variety API URL",
        "requires_input": True,
        "show_variety_removal": True,
    },
    "CA_Close_and_Delete.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api",
        "label": "Base Api Url",
        "requires_input": True,
        "show_ca_close_delete": True,
        "show_batch_config": True,
    },
    "Check_and_Delete_Area_Audit_Outside_India.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/croppable-areas",
        "label": "Base Api Url",
        "requires_input": True,
    },
    "Delete_Task.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/tasks/bulk",
        "label": "Delete API URL",
        "second_base_api_url": "https://cloud.cropin.in/services/farm/api/tasks/croppablearea",
        "label2": "CA TASK API URL",
        "requires_input": True,
    },
    "Delete_Task_No_Batch.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/tasks/bulk",
        "label": "Delete API URL",
        "requires_input": True,
        "show_batch_config": True,
        "unlimited_batch_size": True,
    },
    "Create_Places.py": {
        "base_api_url": "https://cloud.cropin.in/services/farm/api/place",
        "label": "Place API URL",
        "requires_input": True,
        "show_google_api_config": True,
    },
    "Get_Lat_Long_AreaCount.py": {
        "base_api_url": "N/A",
        "label": "N/A",
        "requires_input": True,
        "show_coordinate_order": True,
    },
}

# Fallback config used when a script is not listed in SCRIPT_CONFIGS above.
DEFAULT_SCRIPT_CONFIG = {
    "base_api_url": "https://cloud.cropin.in/services/master/api",
    "label": "Api Url",
    "requires_input": True,
}
