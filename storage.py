import json
import logging
import os
from datetime import datetime, timezone

from google.cloud import storage
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

storage_client = storage.Client()
bucket_name = os.environ.get("GCS_BUCKET_NAME", "miyastudynotes-temp")


def store_file_in_gcs(file_data: bytes, filename: str, submission_id: str, content_type: str) -> str:
    """Store uploaded proof-of-payment file in GCS. Returns the blob path."""
    try:
        bucket = storage_client.bucket(bucket_name)
        sanitized = secure_filename(filename)
        path = f"submissions/{submission_id}/{sanitized}"
        blob = bucket.blob(path)
        blob.metadata = {
            "submission_id": submission_id,
            "original_name": filename,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        blob.upload_from_string(file_data, content_type=content_type)
        logger.info("Uploaded %s", path)
        return path
    except Exception as e:
        logger.error("Upload failed: %s", e)
        raise


def store_submission_metadata(submission_data: dict) -> str:
    """Write submission metadata JSON to GCS. Returns the blob path."""
    try:
        bucket = storage_client.bucket(bucket_name)
        path = f"submissions/{submission_data['submission_id']}/metadata.json"
        blob = bucket.blob(path)
        blob.upload_from_string(json.dumps(submission_data, indent=2), content_type="application/json")
        logger.info("Metadata stored")
        return path
    except Exception as e:
        logger.error("Metadata store failed: %s", e)
        raise


def get_submission_data(submission_id: str) -> dict:
    """Load submission metadata from GCS."""
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(f"submissions/{submission_id}/metadata.json")
    return json.loads(blob.download_as_text())


def update_submission_status(submission_id: str, status: str, extra: dict | None = None) -> dict:
    """Update status (and optional extra fields) in the GCS metadata JSON."""
    data = get_submission_data(submission_id)
    data["status"] = status
    data["processed_at"] = datetime.now(timezone.utc).isoformat()
    if extra:
        data["admin_action"] = extra
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(f"submissions/{submission_id}/metadata.json")
    blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")
    return data
