"""Shared fixtures for all tests."""
import hashlib
import hmac
import os
from unittest.mock import patch

# Minimal env vars so modules import without real GCP credentials
os.environ.setdefault("GCS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("APPROVAL_SECRET", "test-secret")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("BASE_URL", "http://localhost:5000")
os.environ.setdefault("SMTP_HOST", "smtp.example.com")
os.environ.setdefault("SMTP_PORT", "587")
os.environ.setdefault("SMTP_USERNAME", "user")
os.environ.setdefault("SMTP_PASSWORD", "pass")
os.environ.setdefault("FROM_EMAIL", "noreply@example.com")
os.environ.setdefault("GOOGLE_SHEETS_ID", "test-sheet-id")
os.environ.setdefault("EKN110_FOLDER_ID", "folder-ekn110")
os.environ.setdefault("EKN120_FOLDER_ID", "folder-ekn120")
os.environ.setdefault("EKN214_FOLDER_ID", "folder-ekn214")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("ADMINISTRATORS", "admin@example.com")

# Patch GCS client before any module imports it
_storage_patcher = patch("google.cloud.storage.Client")
_storage_patcher.start()

import pytest  # noqa: E402

import main  # noqa: E402


@pytest.fixture
def app():
    main.app.config["TESTING"] = True
    return main.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def pending_submission():
    return {
        "submission_id": "test-sub-001",
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@example.com",
        "phone": "0793688500",
        "module": "EKN110",
        "chapters": ["EKN110-1", "EKN110-2"],
        "total_cost": 50,
        "file_name": "proof.pdf",
        "file_size": 0.5,
        "file_mime_type": "application/pdf",
        "timestamp": "2026-05-08T10:00:00+00:00",
        "status": "pending",
        "gcs_file_path": "submissions/test-sub-001/proof.pdf",
    }


def make_approval_token(submission_id: str) -> str:
    secret = os.environ["APPROVAL_SECRET"].encode()
    return hmac.new(secret, submission_id.encode(), hashlib.sha256).hexdigest()
