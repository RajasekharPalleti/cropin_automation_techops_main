# Google Drive Setup Instructions (Optional)

> **Note**: This setup is completely **optional**. It is only required if you want to enable automatic Google Drive backups.


## Method 1: OAuth 2.0 User Credentials (Recommended)

Follow these steps to generate a `client_secret.json` for authenticating the Backup Manager with your personal Google Drive account. This method uses your own storage quota.

### 1. Setup

You need to provide the `client_secret.json` file.

1.  **Open Google Cloud Console:**
    Go to this link: [https://console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)

2.  **Create Credentials:**
    *   Click the **+ CREATE CREDENTIALS** button at the top.
    *   Select **OAuth client ID**.

3.  **Configure Application Type:**
    *   **Application type**: Select **Desktop app**.
    *   **Name**: Enter a name like `Backup Client`.
    *   Click **CREATE**.

4.  **Download JSON:**
    *   A "OAuth client created" popup will appear.
    *   Click the **DOWNLOAD JSON** button.

5.  **Install:**
    *   Rename the downloaded file to `client_secret.json`.
    *   Move it to: `d:\Cropin Automation Techops\json_config\client_secret.json`

### 2. Configure Test Users (Critical)

Since your app is in "Testing" mode, you must explicitly allow your email address.

1.  Go to **[OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)**.
2.  Scroll down to the **Test users** section.
3.  Click **+ ADD USERS**.
4.  Enter your email address (e.g., `rajasekhar.palletic@gmail.com`).
5.  Click **SAVE**.


---

## Method 2: Service Account (Legacy/Shared Drive)

Follow these steps to generate a new `service_account.json`. Note that Service Accounts have **0 storage quota** and cannot upload to personal folders unless they are part of a Shared Drive (G Suite / Workspace).

### 1. Google Cloud Console Setup
1.  **Go to Google Cloud Console**: [https://console.cloud.google.com/](https://console.cloud.google.com/)
2.  **Create a Project**: 
    *   Click the project dropdown (top left).
    *   Select "New Project".
    *   Name it (e.g., "Cropin Automation").
    *   Click "Create".

### 2. Enable Google Drive API
1.  In the search bar at the top of the console, type **"Google Drive API"** and select it.
2.  Click **"Enable"**.

### 3. Create Service Account
1.  Go to **"Credentials"** (in the left menu).
2.  Click **"Create Credentials"** > **"Service Account"**.
3.  Give it a name (e.g., "backup-bot").
4.  Click **"Create and Continue"**.
5.  (Optional) Select a Role like "Editor" or "Viewer", then click **"Done"**.

### 4. Generate Key (service_account.json)
1.  Click on the email address of the service account you just created (under the Service Accounts section).
2.  Go to the **"Keys"** tab.
3.  Click **"Add Key"** > **"Create new key"**.
4.  Select **JSON** and click **"Create"**.
5.  The file will download automatically.
6.  **Rename this file to** `service_account.json`.
7.  Replace the existing `json_config/service_account.json` in your project with this new file.

### 5. Share Folder Access
1.  Open your `service_account.json` file in a text editor and copy the value of `client_email` (it looks like `backup-bot@project-id.iam.gserviceaccount.com`).
2.  Go to the **Google Drive folder** where you want backups to be stored.
3.  Click **"Share"**.
4.  Paste the **client email** you copied.
5.  Ensure "Editor" permission is selected so the bot can upload files.
6.  Click **"Send"**.

### 6. Update Folder ID (If Changing Folders)
If you are changing the specific folder used for backups:
1.  Open `app/core/backup_manager.py`.
2.  Find the line: `BACKUP_FOLDER_ID = '...'`.
3.  Replace the ID with the ID of your new folder (you can find this in the URL of the Drive folder).
