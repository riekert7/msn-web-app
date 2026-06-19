"""Tests for the admin deny route (/admin/deny/<submission_id>)."""
from unittest.mock import patch

SID = "test-sub-001"


def test_deny_requires_admin(client, pending_submission):
    """Unauthenticated requests must redirect to login."""
    resp = client.post(f"/admin/deny/{SID}")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_deny_updates_status_and_sheets(admin_client, pending_submission):
    """GCS status and Sheets must both be updated to denied."""
    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status") as mock_gcs,
        patch("main.update_google_sheets_status") as mock_sheets,
        patch("main.send_student_denied_email"),
    ):
        admin_client.post(f"/admin/deny/{SID}")

    mock_gcs.assert_called_once_with(SID, "denied")
    mock_sheets.assert_called_once_with(SID, "denied")


def test_deny_sends_student_email(admin_client, pending_submission):
    """Denial email must be sent to the student."""
    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status"),
        patch("main.update_google_sheets_status"),
        patch("main.send_student_denied_email") as mock_email,
    ):
        admin_client.post(f"/admin/deny/{SID}")

    mock_email.assert_called_once_with(pending_submission)


def test_deny_returns_ok(admin_client, pending_submission):
    """Successful deny must return {"ok": true}."""
    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.update_submission_status"),
        patch("main.update_google_sheets_status"),
        patch("main.send_student_denied_email"),
    ):
        resp = admin_client.post(f"/admin/deny/{SID}")

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_deny_returns_error_on_failure(admin_client, pending_submission):
    """Any failure must return 500 with ok=false."""
    with (
        patch("main.get_submission_data", side_effect=Exception("GCS error")),
    ):
        resp = admin_client.post(f"/admin/deny/{SID}")

    assert resp.status_code == 500
    assert resp.get_json()["ok"] is False
