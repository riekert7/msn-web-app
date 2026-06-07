"""Tests for the admin reshare route (/admin/reshare/<submission_id>)."""
from unittest.mock import patch

SID = "test-sub-001"
SHARED_FILES = [{"id": "file-1", "name": "EKN110 - Chapter 1", "chapter": "1"}]


def test_reshare_requires_admin(client, pending_submission):
    """Unauthenticated requests must redirect to login."""
    resp = client.post(f"/admin/reshare/{SID}")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_reshare_calls_drive(admin_client, pending_submission):
    """share_study_materials must be called with the submission's details."""
    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.share_study_materials", return_value=SHARED_FILES) as mock_drive,
        patch("main.update_submission_status"),
        patch("main.update_google_sheets_status"),
        patch("main.send_student_approved_email"),
    ):
        admin_client.post(f"/admin/reshare/{SID}")

    mock_drive.assert_called_once_with(
        pending_submission["email"],
        pending_submission["module"],
        pending_submission["chapters"],
    )


def test_reshare_updates_status_and_sheets(admin_client, pending_submission):
    """GCS is written twice (before Drive for fast refresh, after Drive with file info).
    Sheets is written once before Drive sharing begins."""
    from unittest.mock import call
    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.share_study_materials", return_value=SHARED_FILES),
        patch("main.update_submission_status") as mock_gcs,
        patch("main.update_google_sheets_status") as mock_sheets,
        patch("main.send_student_approved_email"),
    ):
        admin_client.post(f"/admin/reshare/{SID}")

    assert mock_gcs.call_count == 2
    mock_gcs.assert_any_call(SID, "approved")
    mock_gcs.assert_any_call(SID, "approved", {"shared_files": SHARED_FILES})
    mock_sheets.assert_called_once_with(SID, "approved")


def test_reshare_sends_student_email(admin_client, pending_submission):
    """Approval email must be sent with the shared files list."""
    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.share_study_materials", return_value=SHARED_FILES),
        patch("main.update_submission_status"),
        patch("main.update_google_sheets_status"),
        patch("main.send_student_approved_email") as mock_email,
    ):
        admin_client.post(f"/admin/reshare/{SID}")

    mock_email.assert_called_once_with(pending_submission, SHARED_FILES)


def test_reshare_returns_ok_with_count(admin_client, pending_submission):
    """Response must be {"ok": true, "shared_count": N}."""
    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.share_study_materials", return_value=SHARED_FILES),
        patch("main.update_submission_status"),
        patch("main.update_google_sheets_status"),
        patch("main.send_student_approved_email"),
    ):
        resp = admin_client.post(f"/admin/reshare/{SID}")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["shared_count"] == len(SHARED_FILES)


def test_reshare_returns_error_on_drive_failure(admin_client, pending_submission):
    """Drive failure must return 500 with ok=false."""
    with (
        patch("main.get_submission_data", return_value=pending_submission),
        patch("main.share_study_materials", side_effect=Exception("Drive error")),
        patch("main.update_submission_status"),
    ):
        resp = admin_client.post(f"/admin/reshare/{SID}")

    assert resp.status_code == 500
    assert resp.get_json()["ok"] is False
