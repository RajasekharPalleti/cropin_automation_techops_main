# Configuration Directory

This directory (`json_config/`) stores sensitive credential files that are **ignored by Git** for security.

## Required Files

If you have cloned this repository, you must execute the setup steps to generate the following files:

1.  **`client_secret.json`**:
    *   **Required for**: Google Drive Backup Authentication.
    *   **How to get**: Follow the steps in `markdown_files/GDrive_Setup_Instructions.md` to generate an OAuth 2.0 Client ID from Google Cloud Console.

2.  **`token.json`**:
    *   **Auto-generated**: This file is created automatically after the first successful login. You do *not* need to create it manually.

3.  **`service_account.json` (Optional/Legacy)**:
    *   **Only required if**: You are using the legacy Service Account method.
    *   **How to get**: Generate a Service Account key from Google Cloud Console.

> **Note**: Do not commit your personal JSON keys to version control.
