"""Shared fixtures for all tests."""
import json
import os
import pytest
from unittest.mock import MagicMock, patch


# Minimal env vars so main.py imports without crashing
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


# Patch storage_client at import time so main.py doesn't need real GCP credentials
_storage_patcher = patch("google.cloud.storage.Client")
_storage_patcher.start()

import main  # noqa: E402  (must come after env vars + patch)


@pytest.fixture
def app():
    main.app.config["TESTING"] = True
    return main.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def pending_submission():
    """A minimal pending submission dict (matches metadata.json structure)."""
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
    import hmac as _hmac
    import hashlib
    secret = os.environ["APPROVAL_SECRET"].encode()
    return _hmac.new(secret, submission_id.encode(), hashlib.sha256).hexdigest()
