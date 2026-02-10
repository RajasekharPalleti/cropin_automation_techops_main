import os
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

class BackupManager:
    SCOPES = ['https://www.googleapis.com/auth/drive']
    # The folder ID provided by the user
    SCOPES = ['https://www.googleapis.com/auth/drive']
    # The folder ID provided by the user
    BACKUP_FOLDER_ID = '1ftnB8lX8rGHG73EdQcv1eJiJXarlJFr5'
    
    # Embedded Client Configuration to avoid external file dependency
    CLIENT_CONFIG = {
        "installed": {
            "client_id": "962570643063-mnheld5d808mr16upq187tid7dj6l9sa.apps.googleusercontent.com",
            "project_id": "cropin-automation",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": "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",
            "redirect_uris": ["http://localhost"]
        }
    }
    
    TOKEN_FILE = 'json_config/token.json'
    SERVICE_ACCOUNT_FILE = 'json_config/service_account.json'

    def __init__(self):
        self.creds = None
        self.service = None
        self._authenticate()

    def _authenticate(self):
        try:
            # 1. Priority: Service Account (Server/Headless)
            if os.path.exists(self.SERVICE_ACCOUNT_FILE):
                print(f"BackupManager: Found service account file at {self.SERVICE_ACCOUNT_FILE}. Authenticating...")
                try:
                    sa_creds = service_account.Credentials.from_service_account_file(
                        self.SERVICE_ACCOUNT_FILE, scopes=self.SCOPES)
                    sa_service = build('drive', 'v3', credentials=sa_creds)
                    
                    # Verify credentials with a lightweight call
                    sa_service.files().list(pageSize=1, fields="files(id)").execute()
                    
                    self.creds = sa_creds
                    self.service = sa_service
                    print("BackupManager: Successfully authenticated with Google Drive (Service Account).")
                    return
                except Exception as e:
                    print(f"BackupManager: Service Account authentication failed/invalid: {e}. Falling back to User Credentials.")
                    # Fall through to User Credentials logic
                    self.creds = None
                    self.service = None

            # 2. Fallback: User Credentials (Local/Interactive)
            # Load credentials from token file if it exists
            if os.path.exists(self.TOKEN_FILE):
                try:
                    self.creds = Credentials.from_authorized_user_file(self.TOKEN_FILE, self.SCOPES)
                except Exception as e:
                    print(f"BackupManager: Error loading token file: {e}. Deleting invalid token file.")
                    try:
                        os.remove(self.TOKEN_FILE)
                    except:
                        pass
                    self.creds = None
            
            # If there are no (valid) credentials available, let the user log in.
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    print("BackupManager: Refreshing expired user credentials...")
                    try:
                        self.creds.refresh(Request())
                    except Exception as e:
                        print(f"BackupManager: Token refresh failed: {e}. Deleting token and re-authenticating.")
                        if os.path.exists(self.TOKEN_FILE):
                            try:
                                os.remove(self.TOKEN_FILE)
                            except:
                                pass
                        self.creds = None

                # Check again if we have valid creds (refresh might have failed and reset creds to None)
                if not self.creds:
                    print("BackupManager: Initiating new OAuth flow using embedded config...")
                    try:
                        flow = InstalledAppFlow.from_client_config(
                            self.CLIENT_CONFIG, self.SCOPES)
                        # prompt='consent' ensures we get a Refresh Token every time
                        # access_type='offline' is required for background refresh
                        self.creds = flow.run_local_server(
                            port=0,
                            prompt='consent',
                            access_type='offline'
                        )
                        
                        # Save the credentials for the next run
                        with open(self.TOKEN_FILE, 'w') as token:
                            token.write(self.creds.to_json())
                    except Exception as e:
                        print(f"BackupManager: OAuth flow failed: {e}")
                        return

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
