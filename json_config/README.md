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

## 4. Configure Backup Folder ID
After generating your credentials:
1.  Open `app/core/backup_manager.py`.
2.  Find the line: `BACKUP_FOLDER_ID = '...'`.
3.  Replace the ID with the **Folder ID** of the Google Drive folder where you want to store backups.
    *   *You get the ID from the URL of your Drive folder: `drive.google.com/drive/u/0/folders/<THIS_IS_THE_ID>`*.
