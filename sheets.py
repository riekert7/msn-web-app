import logging
import os
import threading
from datetime import datetime, timezone

from google.auth import default
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

_thread_local = threading.local()


def _get_service():
    if not hasattr(_thread_local, "service"):
        creds, _ = default(scopes=["https://www.googleapis.com/auth/spreadsheets"])
        _thread_local.service = build("sheets", "v4", credentials=creds)
    return _thread_local.service


def log_to_google_sheets(submission_data: dict) -> bool:
    """Append a new submission row to the Submissions sheet."""
    sheets_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not sheets_id:
        logger.warning("GOOGLE_SHEETS_ID not configured, skipping")
        return False
    try:
        ts = datetime.fromisoformat(submission_data["timestamp"].replace("Z", "+00:00"))
        row = [
            ts.isoformat(),
            submission_data["submission_id"],
            f"{submission_data['first_name']} {submission_data['last_name']}",
            submission_data["email"],
            submission_data["phone"],
            submission_data["module"],
            ", ".join(submission_data["chapters"]),
            submission_data["total_cost"],
            submission_data["file_name"],
            f"{submission_data['file_size']}MB",
            submission_data["status"],
            "",
            "",
        ]
        _get_service().spreadsheets().values().append(
            spreadsheetId=sheets_id,
            range="Submissions!A:M",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        logger.info("Submission logged")
        return True
    except Exception as e:
        logger.error("Log failed: %s", e)
        return False


def update_google_sheets_status(submission_id: str, status: str, admin_action: dict | None = None) -> bool:
    """Update status (col K) and approval date (col L) for a submission row."""
    sheets_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not sheets_id:
        logger.warning("GOOGLE_SHEETS_ID not configured, skipping status update")
        return False
    try:
        result = _get_service().spreadsheets().values().get(
            spreadsheetId=sheets_id, range="Submissions!A:M"
        ).execute()
        values = result.get("values", [])
        logger.info("update_google_sheets_status: %d rows found for %s", len(values), submission_id)

        row_index = next(
            (i + 1 for i, row in enumerate(values) if len(row) > 1 and row[1] == submission_id),
            None,
        )
        if row_index is None:
            logger.error("submission_id=%s not found; cannot update", submission_id)
            return False

        now = datetime.now(timezone.utc).isoformat()
        _get_service().spreadsheets().values().batchUpdate(
            spreadsheetId=sheets_id,
            body={
                "valueInputOption": "RAW",
                "data": [
                    {"range": f"Submissions!K{row_index}", "values": [[status]]},
                    {"range": f"Submissions!L{row_index}", "values": [[now]]},
                ],
            },
        ).execute()
        logger.info("Updated %s -> %s at row %d", submission_id, status, row_index)
        return True
    except Exception as e:
        logger.error("Status update failed for %s: %s", submission_id, e)
        return False
