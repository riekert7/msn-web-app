import os
from datetime import datetime, timezone

from google.auth import default
from googleapiclient.discovery import build


def log_to_google_sheets(submission_data: dict) -> bool:
    """Append a new submission row to the Submissions sheet."""
    sheets_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not sheets_id:
        print("[SHEETS] GOOGLE_SHEETS_ID not configured, skipping")
        return False
    try:
        creds, _ = default(scopes=["https://www.googleapis.com/auth/spreadsheets"])
        service = build("sheets", "v4", credentials=creds)
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
            "",  # approval date
            "",  # admin notes
        ]
        service.spreadsheets().values().append(
            spreadsheetId=sheets_id,
            range="Submissions!A:M",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        print("[SHEETS] Submission logged")
        return True
    except Exception as e:
        print(f"[SHEETS] Log failed: {e}")
        return False


def update_google_sheets_status(submission_id: str, status: str, admin_action: dict | None = None) -> bool:
    """Update status (col K) and approval date (col L) for a submission row."""
    sheets_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not sheets_id:
        print("[SHEETS] GOOGLE_SHEETS_ID not configured, skipping status update")
        return False
    try:
        creds, _ = default(scopes=["https://www.googleapis.com/auth/spreadsheets"])
        service = build("sheets", "v4", credentials=creds)

        result = service.spreadsheets().values().get(
            spreadsheetId=sheets_id, range="Submissions!A:M"
        ).execute()
        values = result.get("values", [])

        row_index = None
        for i, row in enumerate(values):
            if len(row) > 1 and row[1] == submission_id:
                row_index = i + 1
                break

        if row_index is None:
            print(f"[SHEETS] submission_id={submission_id} not found; cannot update")
            return False

        now = datetime.now(timezone.utc).isoformat()
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=sheets_id,
            body={
                "valueInputOption": "RAW",
                "data": [
                    {"range": f"Submissions!K{row_index}", "values": [[status]]},
                    {"range": f"Submissions!L{row_index}", "values": [[now]]},
                ],
            },
        ).execute()
        print(f"[SHEETS] Updated {submission_id} → {status} at row {row_index}")
        return True
    except Exception as e:
        print(f"[SHEETS] Status update failed for {submission_id}: {e}")
        return False
