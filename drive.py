import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from google.auth import default
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

_FOLDER_IDS = {
    "EKN110": lambda: os.environ.get("EKN110_FOLDER_ID"),
    "EKN120": lambda: os.environ.get("EKN120_FOLDER_ID"),
    "EKN214": lambda: os.environ.get("EKN214_FOLDER_ID"),
}


def _get_service():
    creds, _ = default(scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds)


def _chapter_number_exact_in_name(name: str, module: str, chapter_number: str) -> bool:
    """True only when the chapter number is exact — 'Chapter 1' must not match 'Chapter 10'."""
    pattern = re.escape(module) + r" - Chapter " + re.escape(chapter_number) + r"(?:\D|$)"
    return re.search(pattern, name) is not None


def _find_chapter_files(parent_folder_id: str, module: str, chapter_number: str) -> list:
    """Return Drive file dicts matching '<MODULE> - Chapter <N>' (exact chapter number)."""
    if not parent_folder_id:
        return []
    pattern = f"{module} - Chapter {chapter_number}"
    q = f"parents in '{parent_folder_id}' and name contains '{pattern}' and trashed=false"
    res = _get_service().files().list(
        q=q,
        fields="files(id, name)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    ).execute()
    files = res.get("files", [])
    return [f for f in files if _chapter_number_exact_in_name(f.get("name", ""), module, chapter_number)]


def _grant_permission(file_id: str, file_name: str, chapter: str, email: str) -> dict | None:
    """Grant reader access to one file. Each call uses the thread-local service client."""
    try:
        _get_service().permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "user", "emailAddress": email},
            sendNotificationEmail=False,
            supportsAllDrives=True,
        ).execute(num_retries=3)
        logger.info("Shared %s (id=%s) with %s", file_name, file_id, email)
        return {"id": file_id, "name": file_name, "chapter": chapter}
    except HttpError as e:
        logger.error("Permission error for %s: %s", file_id, e)
        return None


def share_study_materials(email: str, module: str, chapters: list) -> list:
    """Share the requested chapter files from Drive with the student.

    File discovery is sequential; permission grants run concurrently —
    each worker thread gets its own Drive client via threading.local().
    """
    folder_id = _FOLDER_IDS.get(module, lambda: None)()
    if not folder_id:
        raise ValueError(f"No Drive folder configured for module: {module}")

    logger.info("Sharing %s chapters=%s with %s", module, chapters, email)

    # Discover all files first (sequential — one list call per chapter)
    file_chapter_pairs = []
    for chapter in chapters:
        try:
            num = chapter.split("-")[1]
            files = _find_chapter_files(folder_id, module, num)
            if not files:
                logger.warning("No files found for %s chapter %s", module, num)
            else:
                file_chapter_pairs.extend((f, num) for f in files)
        except Exception as e:
            logger.error("Error finding files for chapter %s: %s", chapter, e)

    if not file_chapter_pairs:
        return []

    # Grant all permissions concurrently — one thread per file
    shared = []
    with ThreadPoolExecutor(max_workers=min(len(file_chapter_pairs), 10)) as pool:
        futures = {
            pool.submit(_grant_permission, f["id"], f["name"], num, email): f["name"]
            for f, num in file_chapter_pairs
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                shared.append(result)

    return shared
