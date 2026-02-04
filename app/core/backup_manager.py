import os
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

class BackupManager:
    SCOPES = ['https://www.googleapis.com/auth/drive']
    # The folder ID provided by the user
    BACKUP_FOLDER_ID = '1ftnB8lX8rGHG73EdQcv1eJiJXarlJFr5'
    CLIENT_SECRET_FILE = 'json_config/client_secret.json'
    TOKEN_FILE = 'json_config/token.json'

    def __init__(self):
        self.creds = None
        self.service = None
        self._authenticate()

    def _authenticate(self):
        try:
            # Load credentials from token file if it exists
            if os.path.exists(self.TOKEN_FILE):
                self.creds = Credentials.from_authorized_user_file(self.TOKEN_FILE, self.SCOPES)
            
            # If there are no (valid) credentials available, let the user log in.
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    print("BackupManager: Refreshing expired credentials...")
                    self.creds.refresh(Request())
                else:
                    if os.path.exists(self.CLIENT_SECRET_FILE):
                        print("BackupManager: Initiating new OAuth flow...")
                        flow = InstalledAppFlow.from_client_secrets_file(
                            self.CLIENT_SECRET_FILE, self.SCOPES)
                        self.creds = flow.run_local_server(port=0)
                    else:
                        print(f"BackupManager: Client secret file not found at {self.CLIENT_SECRET_FILE}")
                        return

                # Save the credentials for the next run
                with open(self.TOKEN_FILE, 'w') as token:
                    token.write(self.creds.to_json())
            
            self.service = build('drive', 'v3', credentials=self.creds)
            print("BackupManager: Successfully authenticated with Google Drive (User Credentials).")

        except Exception as e:
            print(f"BackupManager: Authentication failed: {e}")

    def upload_file(self, file_path, custom_name=None):
        """Uploads a file to the configured Google Drive folder."""
        if not self.service:
            print("BackupManager: Service not initialized. Skipping upload.")
            return None

        if not os.path.exists(file_path):
            print(f"BackupManager: File not found {file_path}")
            return None

        try:
            file_metadata = {
                'name': custom_name if custom_name else os.path.basename(file_path),
                'parents': [self.BACKUP_FOLDER_ID]
            }
            media = MediaFileUpload(file_path, resumable=True)
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()
            
            print(f"BackupManager: File ID: {file.get('id')} uploaded.")
            return file
        except Exception as e:
            print(f"BackupManager: Upload failed: {e}")
            return None

    def list_files(self, page_size=100, page_token=None):
        """Lists files in the backup folder with pagination."""
        if not self.service:
            print("BackupManager: Service not initialized. Skipping list.")
            return {"uploaded": [], "downloaded": [], "nextPageToken": None}

        try:
            results = self.service.files().list(
                q=f"'{self.BACKUP_FOLDER_ID}' in parents and trashed=false",
                pageSize=page_size,
                pageToken=page_token,
                fields="nextPageToken, files(id, name, createdTime, size, webContentLink, webViewLink, mimeType)",
                orderBy="createdTime desc"
            ).execute()
            
            items = results.get('files', [])
            next_page_token = results.get('nextPageToken')
            
            uploaded_files = []
            downloaded_files = []
            
            for item in items:
                # Classify based on filename convention
                # Inputs start with 'input_'
                # Outputs usually end with '_Output.xlsx'
                
                name = item.get('name', '')
                file_obj = {
                    'id': item.get('id'),
                    'name': name,
                    'createdTime': item.get('createdTime'),
                    'size': item.get('size'),
                    'webViewLink': item.get('webViewLink'),
                    'webContentLink': item.get('webContentLink') # This allows direct download
                }
                
                if name.startswith('input_'):
                    uploaded_files.append(file_obj)
                else:
                    # Treat everything else as downloaded/output files
                    downloaded_files.append(file_obj)
                    
            return {
                "uploaded": uploaded_files,
                "downloaded": downloaded_files,
                "nextPageToken": next_page_token
            }

        except Exception as e:
            print(f"BackupManager: List files failed: {e}")
            return {"uploaded": [], "downloaded": [], "nextPageToken": None}

    def cleanup_old_files(self, days=90):
        """Deletes files older than the specified number of days."""
        if not self.service:
            return

        print(f"BackupManager: Starting cleanup of files older than {days} days...")
        try:
            # Calculate the cutoff date
            cutoff_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
            
            # Query for files created before the cutoff date
            query = f"'{self.BACKUP_FOLDER_ID}' in parents and trashed=false and createdTime < '{cutoff_date}'"
            
            results = self.service.files().list(
                q=query,
                fields="files(id, name, createdTime)"
            ).execute()
            
            files_to_delete = results.get('files', [])
            
            if not files_to_delete:
                print("BackupManager: No old files found to delete.")
                return

            print(f"BackupManager: Found {len(files_to_delete)} files to delete.")
            
            for file in files_to_delete:
                try:
                    print(f"BackupManager: Deleting old file {file.get('name')} (ID: {file.get('id')})...")
                    self.service.files().delete(fileId=file.get('id')).execute()
                except Exception as e:
                    print(f"BackupManager: Failed to delete file {file.get('id')}: {e}")
                    
            print("BackupManager: Cleanup complete.")
            
        except Exception as e:
            print(f"BackupManager: Cleanup failed: {e}")
