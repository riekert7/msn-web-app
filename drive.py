import os
import re

from google.auth import default
from googleapiclient.discovery import build

_FOLDER_IDS = {
    "EKN110": lambda: os.environ.get("EKN110_FOLDER_ID"),
    "EKN120": lambda: os.environ.get("EKN120_FOLDER_ID"),
    "EKN214": lambda: os.environ.get("EKN214_FOLDER_ID"),
}


def _get_drive_service():
    creds, _ = default(scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds)


def _chapter_number_exact_in_name(name: str, module: str, chapter_number: str) -> bool:
    """True only when the chapter number is exact — 'Chapter 1' must not match 'Chapter 10'."""
    pattern = re.escape(module) + r" - Chapter " + re.escape(chapter_number) + r"(?:\D|$)"
    return re.search(pattern, name) is not None


def _find_chapter_files(drive, parent_folder_id: str, module: str, chapter_number: str) -> list:
    """Return Drive file dicts matching '<MODULE> - Chapter <N>' (exact chapter number)."""
    if not parent_folder_id:
        return []
    pattern = f"{module} - Chapter {chapter_number}"
    q = f"parents in '{parent_folder_id}' and name contains '{pattern}' and trashed=false"
    res = drive.files().list(
        q=q,
        fields="files(id, name)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    ).execute()
    files = res.get("files", [])
    return [f for f in files if _chapter_number_exact_in_name(f.get("name", ""), module, chapter_number)]


def share_study_materials(email: str, module: str, chapters: list) -> list:
    """Share the requested chapter files from Drive with the student. Returns shared file info."""
    from googleapiclient.errors import HttpError

    folder_id = _FOLDER_IDS.get(module, lambda: None)()
    if not folder_id:
        raise ValueError(f"No Drive folder configured for module: {module}")

    print(f"[DRIVE] Sharing {module} chapters={chapters} with {email}")
    drive = _get_drive_service()
    shared = []

    for chapter in chapters:
        try:
            num = chapter.split("-")[1]
            files = _find_chapter_files(drive, folder_id, module, num)
            if not files:
                print(f"[DRIVE] No files found for {module} chapter {num}")
                continue
            for f in files:
                try:
                    drive.permissions().create(
                        fileId=f["id"],
                        body={"role": "reader", "type": "user", "emailAddress": email},
                        sendNotificationEmail=False,
                        supportsAllDrives=True,
                    ).execute(num_retries=3)
                    print(f"[DRIVE] Shared {f['name']} (id={f['id']}) with {email}")
                    shared.append({"id": f["id"], "name": f["name"], "chapter": num})
                except HttpError as e:
                    print(f"[DRIVE] Permission error for {f['id']}: {e}")
        except Exception as e:
            print(f"[DRIVE] Error sharing chapter {chapter}: {e}")

    return shared
