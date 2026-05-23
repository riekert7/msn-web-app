import os
import json

from google.auth import default
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from dotenv import load_dotenv

load_dotenv(".env")

SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
USER_TO_REMOVE = "###@gmail.com"

# Get folder IDs from environment
FOLDER_IDS = [
    os.environ.get("EKN110_FOLDER_ID"),
    os.environ.get("EKN120_FOLDER_ID"),
    os.environ.get("EKN214_FOLDER_ID"),
]

def get_drive_service():
    """Authenticate as service account and return Drive API client."""
    creds, _ = default(scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds)

def list_files_in_folder(drive, folder_id):
    """List all non-trashed files in a folder."""
    results = []
    page_token = None
    while True:
        q = f"parents in '{folder_id}' and trashed = false"
        response = drive.files().list(
            q=q,
            fields="nextPageToken, files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageToken=page_token,
        ).execute()
        results.extend(response.get("files", []))
        page_token = response.get('nextPageToken', None)
        if page_token is None:
            break
    return results

def get_permissions(drive, file_id):
    """Return all permissions for a file."""
    return drive.permissions().list(
        fileId=file_id,
        fields="permissions(id,emailAddress,role)",
        supportsAllDrives=True,
    ).execute().get("permissions", [])

def remove_user_permission(drive, file_id, perm_id):
    """Remove a specific permission from a file."""
    try:
        drive.permissions().delete(
            fileId=file_id,
            permissionId=perm_id,
            supportsAllDrives=True
        ).execute()
        print(f"Removed permission {perm_id} on file {file_id}")
    except HttpError as err:
        print(f"Failed to remove permission {perm_id} on {file_id}: {err}")

def main():
    drive = get_drive_service()
    for folder_id in FOLDER_IDS:
        if not folder_id:
            continue
        print(f"Processing folder: {folder_id}")
        files = list_files_in_folder(drive, folder_id)
        print(f"- Found {len(files)} files in folder.")
        for f in files:
            perms = get_permissions(drive, f["id"])
            for p in perms:
                if p.get("emailAddress") == USER_TO_REMOVE:
                    print(f"Found {USER_TO_REMOVE} on file {f['name']} ({f['id']}) as {p['role']}. Revoking...")
                    remove_user_permission(drive, f["id"], p["id"])
    print("Done.")

if __name__ == "__main__":
    main()