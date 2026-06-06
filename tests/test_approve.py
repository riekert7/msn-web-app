import threading
import time
from unittest.mock import MagicMock, patch

from tests.conftest import make_approval_token

SID = "test-sub-001"


def test_approve_invalid_token(client):
    resp = client.get(f"/approve/{SID}?token=bad-token")
    assert resp.status_code == 403


def test_approve_missing_token(client):
    resp = client.get(f"/approve/{SID}")
    assert resp.status_code == 403


def test_approve_already_processed(client, pending_submission):
    already_approved = {**pending_submission, "status": "approved"}
    with patch("main.get_submission_data", return_value=already_approved):
        token = make_approval_token(SID)
        resp = client.get(f"/approve/{SID}?token={token}")
    assert resp.status_code == 200
    assert b"Already processed" in resp.data


def test_approve_gcs_status_updated_synchronously(client, pending_submission):
    """GCS must be written to 'approved' before the response returns — prevents double-click."""
    status_written = []

    def fake_update_status(sid, status, extra=None):
        status_written.append(status)
        return {**pending_submission, "status": status}

    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status", side_effect=fake_update_status),
        patch("main._executor") as mock_executor,
    ):
        mock_executor.submit = MagicMock()
        token = make_approval_token(SID)
        resp = client.get(f"/approve/{SID}?token={token}")

    assert resp.status_code == 200
    assert "approved" in status_written


def test_approve_returns_before_background_work_completes(client, pending_submission):
    """HTTP response must arrive before slow Drive work finishes (< 0.5s)."""
    slow_drive_done = threading.Event()

    def slow_drive(*args, **kwargs):
        time.sleep(1.0)
        slow_drive_done.set()
        return []

    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status", return_value={**pending_submission, "status": "approved"}),
        patch("tasks.share_study_materials", side_effect=slow_drive),
        patch("tasks.update_google_sheets_status"),
        patch("tasks.update_submission_status", return_value={**pending_submission, "status": "approved"}),
        patch("tasks.send_student_approved_email"),
    ):
        token = make_approval_token(SID)
        t0 = time.monotonic()
        resp = client.get(f"/approve/{SID}?token={token}")
        elapsed = time.monotonic() - t0

    assert resp.status_code == 200
    assert elapsed < 0.5, f"Response took {elapsed:.2f}s — approve route must return immediately"


def test_approve_background_calls_drive_then_email(client, pending_submission):
    """Background task must call share_study_materials BEFORE send_student_approved_email."""
    call_order = []

    def track_drive(*args, **kwargs):
        call_order.append("drive")
        return [{"id": "file-1", "name": "Chapter 1", "chapter": "1"}]

    def track_email(*args, **kwargs):
        call_order.append("email")
        return True

    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status", return_value={**pending_submission, "status": "approved"}),
        patch("tasks.share_study_materials", side_effect=track_drive),
        patch("tasks.update_google_sheets_status"),
        patch("tasks.update_submission_status", return_value={**pending_submission, "status": "approved"}),
        patch("tasks.send_student_approved_email", side_effect=track_email),
    ):
        token = make_approval_token(SID)
        resp = client.get(f"/approve/{SID}?token={token}")
        time.sleep(0.3)

    assert resp.status_code == 200
    assert call_order.index("drive") < call_order.index("email"), f"Expected drive before email, got {call_order}"


def test_approve_background_calls_sheets(client, pending_submission):
    """Background task must call update_google_sheets_status."""
    sheets_calls = []

    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status", return_value={**pending_submission, "status": "approved"}),
        patch("tasks.share_study_materials", return_value=[]),
        patch("tasks.update_google_sheets_status", side_effect=lambda *a, **kw: sheets_calls.append(a)),
        patch("tasks.update_submission_status", return_value={**pending_submission, "status": "approved"}),
        patch("tasks.send_student_approved_email"),
    ):
        token = make_approval_token(SID)
        resp = client.get(f"/approve/{SID}?token={token}")
        time.sleep(0.3)

    assert resp.status_code == 200
    assert len(sheets_calls) >= 1, "update_google_sheets_status must be called in background"


def test_approve_double_click_idempotent(client, pending_submission):
    """Drive sharing must only run once even if Approve is clicked twice."""
    drive_calls = []
    submission_state = {"data": pending_submission}

    def fake_get(sid):
        return submission_state["data"]

    def fake_update(sid, status, extra=None):
        submission_state["data"] = {**submission_state["data"], "status": status}
        return submission_state["data"]

    def fake_drive(*args, **kwargs):
        drive_calls.append(1)
        return []

    token = make_approval_token(SID)
    with (
        patch("main.get_submission_data", side_effect=fake_get),
        patch("main.update_submission_status", side_effect=fake_update),
        patch("tasks.share_study_materials", side_effect=fake_drive),
        patch("tasks.update_google_sheets_status"),
        patch("tasks.update_submission_status", return_value={**pending_submission, "status": "approved"}),
        patch("tasks.send_student_approved_email"),
    ):
        client.get(f"/approve/{SID}?token={token}")
        time.sleep(0.3)
        resp2 = client.get(f"/approve/{SID}?token={token}")

    assert b"Already processed" in resp2.data
    assert len(drive_calls) == 1, "Drive must only be called once even if Approve is clicked twice"
