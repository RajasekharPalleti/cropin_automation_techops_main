# Google Cloud Project & Credential Cleanup Guide

This guide details the steps to remove the Google Cloud Project and credentials (Service Account & OAuth) created for this automation tool.

> [!WARNING]
> **These actions are irreversible.** Deleting a project will shut down all resources and API services within it.

## Option 1: Delete the Entire Project (Recommended)
If you created a specific project solely for this automation (e.g., `Cropin-Automation`), the easiest way to clean up is to shut down the entire project.

1.  Go to the **[Google Cloud Console Dashboard](https://console.cloud.google.com/home/dashboard)**.
2.  Ensure the correct project is selected in the top bar dropdown.
3.  Click on the **three-dot menu** (⋮) at the top right of the dashboard card "Project info" or go to **IAM & Admin** > **Settings**.
4.  Click **Shut down**.
5.  Enter the **Project ID** shown on the screen to confirm.
6.  Click **Shut down** again.

*This will delete all OAuth clients, Service Accounts, and associated data for this project.*

---

## Option 2: Delete Specific Credentials Only
If you are using a shared project and only want to remove the credentials created for this tool:

### 1. Delete OAuth 2.0 Client (User Credentials)
1.  Navigate to **[APIs & Services > Credentials](https://console.cloud.google.com/apis/credentials)**.
2.  Under **OAuth 2.0 Client IDs**, find the client you created (e.g., `Desktop-Client` or `Python-Automation`).
3.  Click the **trash icon** next to it.
4.  Confirm deletion.

### 2. Delete Service Account (Legacy Method)
1.  On the same **Credentials** page, look under **Service Accounts**.
2.  Find the service account (email ends in `@<project-id>.iam.gserviceaccount.com`).
3.  Click the **pencil icon** (Edit) or click the email address.
4.  Click **DELETE** at the top of the detail page.
5.  Confirm deletion.

### 3. Remove Test Users (If App is in Testing)
1.  Navigate to **[APIs & Services > OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)**.
2.  Under **Test users**, find your email address.
3.  Click the **trash icon** next to it to revoke access for testing.

---

## Local Cleanup
After cleaning up the cloud resources, you should delete the local credential files to prevent the application from trying to use invalid keys.

1.  **Stop the automation server**.
2.  Navigate to the `app/` folder in your project directory.
3.  Delete the following files:
    *   `client_secret.json` (The OAuth configuration file)
    *   `token.json` (The generated user session token)
    *   `service_account_credentials.json` (If you used the legacy method)
