"""TDD tests for the /approve route.

Red phase: these tests describe the desired behaviour AFTER the async refactor.
Run `pytest` now to see them fail; implement in main.py to make them green.
"""
import threading
import time
from unittest.mock import MagicMock, patch

from tests.conftest import make_approval_token

SID = "test-sub-001"


# ---------------------------------------------------------------------------
# Token / guard tests (these already pass with existing code)
# ---------------------------------------------------------------------------

def test_approve_invalid_token(client):
    """Bad or missing token must return 403."""
    resp = client.get(f"/approve/{SID}?token=bad-token")
    assert resp.status_code == 403


def test_approve_missing_token(client):
    resp = client.get(f"/approve/{SID}")
    assert resp.status_code == 403


def test_approve_already_processed(client, pending_submission):
    """Submission already approved/denied must return 200 with 'Already processed'."""
    already_approved = {**pending_submission, "status": "approved"}
    with patch("main.get_submission_data", return_value=already_approved):
        token = make_approval_token(SID)
        resp = client.get(f"/approve/{SID}?token={token}")
    assert resp.status_code == 200
    assert b"Already processed" in resp.data


# ---------------------------------------------------------------------------
# Async behaviour tests (these FAIL before the refactor)
# ---------------------------------------------------------------------------

def test_approve_gcs_status_updated_synchronously(client, pending_submission):
    """GCS status must be written to 'approved' BEFORE the response is returned.

    This prevents double-processing if the admin clicks twice quickly.
    """
    status_written = []

    def fake_update_status(sid, status, extra=None):
        status_written.append(status)
        return {**pending_submission, "status": status}

    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status", side_effect=fake_update_status),
        patch("main.share_study_materials", return_value=[]),
        patch("main.update_google_sheets_status"),
        patch("main.send_student_approved_email"),
        patch("main._executor", create=True) as mock_executor,
    ):
        mock_executor.submit = MagicMock()
        token = make_approval_token(SID)
        resp = client.get(f"/approve/{SID}?token={token}")

    assert resp.status_code == 200
    # The synchronous status write must have happened
    assert "approved" in status_written


def test_approve_returns_before_background_work_completes(client, pending_submission):
    """The HTTP response must arrive before the (slow) background work finishes.

    We simulate slow Drive API by making share_study_materials sleep 1s.
    The response must come back in under 0.5s.
    """
    slow_drive_started = threading.Event()
    slow_drive_done = threading.Event()

    def slow_drive(*args, **kwargs):
        slow_drive_started.set()
        time.sleep(1.0)
        slow_drive_done.set()
        return []

    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status", return_value={**pending_submission, "status": "approved"}),
        patch("main.share_study_materials", side_effect=slow_drive),
        patch("main.update_google_sheets_status"),
        patch("main.send_student_approved_email"),
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
        patch("main.share_study_materials", side_effect=track_drive),
        patch("main.update_google_sheets_status"),
        patch("main.send_student_approved_email", side_effect=track_email),
    ):
        token = make_approval_token(SID)
        resp = client.get(f"/approve/{SID}?token={token}")
        # Allow background thread to finish
        time.sleep(0.3)

    assert resp.status_code == 200
    assert call_order == ["drive", "email"], f"Expected drive→email, got {call_order}"


def test_approve_background_calls_sheets(client, pending_submission):
    """Background task must call update_google_sheets_status."""
    sheets_calls = []

    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status", return_value={**pending_submission, "status": "approved"}),
        patch("main.share_study_materials", return_value=[]),
        patch("main.update_google_sheets_status", side_effect=lambda *a, **kw: sheets_calls.append(a)),
        patch("main.send_student_approved_email"),
    ):
        token = make_approval_token(SID)
        resp = client.get(f"/approve/{SID}?token={token}")
        time.sleep(0.3)

    assert resp.status_code == 200
    assert len(sheets_calls) >= 1, "update_google_sheets_status must be called in background"


def test_approve_double_click_idempotent(client, pending_submission):
    """Clicking Approve twice must not re-run Drive sharing.

    First click marks GCS as 'approved'; second click must see status != pending
    and return 'Already processed' without calling Drive.
    """
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
        patch("main.share_study_materials", side_effect=fake_drive),
        patch("main.update_google_sheets_status"),
        patch("main.send_student_approved_email"),
    ):
        client.get(f"/approve/{SID}?token={token}")
        time.sleep(0.3)
        resp2 = client.get(f"/approve/{SID}?token={token}")

    assert b"Already processed" in resp2.data
    assert len(drive_calls) == 1, "Drive must only be called once even if Approve is clicked twice"
