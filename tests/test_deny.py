import time
from unittest.mock import MagicMock, patch

from tests.conftest import make_approval_token

SID = "test-sub-001"


def test_deny_invalid_token(client):
    resp = client.get(f"/deny/{SID}?token=wrong")
    assert resp.status_code == 403


def test_deny_already_processed(client, pending_submission):
    denied = {**pending_submission, "status": "denied"}
    with patch("main.get_submission_data", return_value=denied):
        token = make_approval_token(SID)
        resp = client.get(f"/deny/{SID}?token={token}")
    assert resp.status_code == 200
    assert b"Already processed" in resp.data


def test_deny_gcs_status_updated_synchronously(client, pending_submission):
    """GCS must be written to 'denied' before the response returns — prevents double-click."""
    status_written = []

    def fake_update(sid, status, extra=None):
        status_written.append(status)
        return {**pending_submission, "status": status}

    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status", side_effect=fake_update),
        patch("main._executor") as mock_executor,
    ):
        mock_executor.submit = MagicMock()
        token = make_approval_token(SID)
        resp = client.get(f"/deny/{SID}?token={token}")

    assert resp.status_code == 200
    assert "denied" in status_written


def test_deny_returns_before_background_work_completes(client, pending_submission):
    """Deny response must arrive in < 0.5s even when email is slow."""
    import threading
    slow_started = threading.Event()

    def slow_email(*args, **kwargs):
        slow_started.set()
        time.sleep(1.0)
        return True

    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status", return_value={**pending_submission, "status": "denied"}),
        patch("tasks.update_google_sheets_status"),
        patch("tasks.send_student_denied_email", side_effect=slow_email),
    ):
        token = make_approval_token(SID)
        t0 = time.monotonic()
        resp = client.get(f"/deny/{SID}?token={token}")
        elapsed = time.monotonic() - t0

    assert resp.status_code == 200
    assert elapsed < 0.5, f"Deny took {elapsed:.2f}s — must return immediately"


def test_deny_background_calls_sheets_and_email(client, pending_submission):
    """Background task must call Sheets update and send denied email."""
    calls = []

    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status", return_value={**pending_submission, "status": "denied"}),
        patch("tasks.update_google_sheets_status", side_effect=lambda *a, **kw: calls.append("sheets")),
        patch("tasks.send_student_denied_email", side_effect=lambda *a, **kw: calls.append("email")),
    ):
        token = make_approval_token(SID)
        resp = client.get(f"/deny/{SID}?token={token}")
        time.sleep(0.3)

    assert resp.status_code == 200
    assert "sheets" in calls
    assert "email" in calls
