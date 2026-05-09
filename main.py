import atexit
import json
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import sentry_sdk
from flask import Flask, jsonify, render_template, request
from sentry_sdk.integrations.flask import FlaskIntegration

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

from drive import share_study_materials
from email_utils import (
    send_student_approved_email,
    send_student_denied_email,
    send_submission_emails_in_background,
    verify_approval_token,
)
from sheets import log_to_google_sheets, update_google_sheets_status
from storage import (
    get_submission_data,
    store_file_in_gcs,
    store_submission_metadata,
    update_submission_status,
)

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[FlaskIntegration()],
    traces_sample_rate=0.2,
    send_default_pii=False,
    environment=os.environ.get("FLASK_ENV", "production"),
)

app = Flask(__name__, static_folder="static", template_folder="templates")

_executor = ThreadPoolExecutor(max_workers=4)
atexit.register(_executor.shutdown, wait=True)

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    return render_template("index.html")


@app.get("/form")
def form():
    return render_template("form.html")


# ---------------------------------------------------------------------------
# Form submission
# ---------------------------------------------------------------------------

@app.post("/submit")
def submit():
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    try:
        if "proofOfPayment" not in request.files:
            return jsonify({"error": "Proof of payment file is required"}), 400, headers

        file = request.files["proofOfPayment"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400, headers
        if not _allowed_file(file.filename):
            return jsonify({"error": "Invalid file type. Only PDF, JPG, and PNG files are allowed."}), 400, headers

        file_data = file.read()
        if len(file_data) > MAX_FILE_SIZE:
            return jsonify({"error": "File size exceeds 5MB limit"}), 400, headers

        required_fields = ["firstName", "lastName", "email", "phone", "module", "chapters", "totalCost"]
        for field in required_fields:
            if field not in request.form:
                return jsonify({"error": f"Missing required field: {field}"}), 400, headers

        submission_id = str(uuid.uuid4())

        try:
            chapters_raw = request.form["chapters"]
            chapters = json.loads(chapters_raw) if isinstance(chapters_raw, str) else [chapters_raw]
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid chapters format"}), 400, headers

        submission_data = {
            "submission_id": submission_id,
            "first_name": request.form["firstName"].strip(),
            "last_name": request.form["lastName"].strip(),
            "email": request.form["email"].strip().lower(),
            "phone": request.form["phone"].strip(),
            "module": request.form["module"],
            "chapters": chapters,
            "total_cost": int(request.form["totalCost"]),
            "file_name": file.filename,
            "file_size": round(len(file_data) / 1024 / 1024, 2),
            "file_mime_type": file.content_type,
            "timestamp": request.form.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "status": "pending",
            "gcs_file_path": None,
        }

        logger.info("Processing submission: %s", submission_id)
        gcs_path = store_file_in_gcs(file_data, file.filename, submission_id, file.content_type)
        submission_data["gcs_file_path"] = gcs_path
        store_submission_metadata(submission_data)
        log_to_google_sheets(submission_data)

        _executor.submit(
            send_submission_emails_in_background,
            submission_data,
            file_data,
            file.filename or "proof",
            file.content_type or "application/octet-stream",
        )

        return jsonify({
            "success": True,
            "submission_id": submission_id,
            "message": "Submission received and notification sent for approval",
            "data": {
                "submission_id": submission_id,
                "email": submission_data["email"],
                "module": submission_data["module"],
                "chapters_count": len(submission_data["chapters"]),
                "total_cost": submission_data["total_cost"],
            },
        }), 200, headers

    except Exception as e:
        logger.error("Submit error: %s", e)
        return jsonify({"error": "Internal server error", "message": "Failed to process submission. Please try again."}), 500, headers


# ---------------------------------------------------------------------------
# Admin approve / deny
# ---------------------------------------------------------------------------

def _approve_background(submission_id: str, data: dict) -> None:
    """Drive sharing → GCS update with file info → Sheets → student email."""
    try:
        shared = share_study_materials(data["email"], data["module"], data["chapters"])
        update_submission_status(submission_id, "approved", {"shared_files": shared})
        update_google_sheets_status(submission_id, "approved")
        send_student_approved_email(data, shared)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"[APPROVE] Background error for {submission_id}: {e}")


@app.get("/approve/<submission_id>")
def approve(submission_id: str):
    """Admin approve link — token verified, GCS updated synchronously, heavy work backgrounded."""
    token = request.args.get("token")
    if not verify_approval_token(submission_id, token or ""):
        return render_template("action_message.html", title="Invalid or expired link", message="This approval link is invalid or has expired."), 403

    try:
        data = get_submission_data(submission_id)
        if data.get("status") not in ("pending", None):
            return render_template("action_message.html", title="Already processed", message=f"This request was already {data.get('status')}."), 200

        update_submission_status(submission_id, "approved")
        _executor.submit(_approve_background, submission_id, data)
        return render_template("approved.html"), 200

    except Exception as e:
        logger.error("Approve error for %s: %s", submission_id, e)
        return render_template("action_message.html", title="Error", message=f"Something went wrong: {e}"), 500


def _deny_background(submission_id: str, data: dict) -> None:
    """Sheets update → student denied email."""
    try:
        update_google_sheets_status(submission_id, "denied")
        send_student_denied_email(data)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"[DENY] Background error for {submission_id}: {e}")


@app.get("/deny/<submission_id>")
def deny(submission_id: str):
    """Admin deny link — token verified, GCS updated synchronously, email/Sheets backgrounded."""
    token = request.args.get("token")
    if not verify_approval_token(submission_id, token or ""):
        return render_template("action_message.html", title="Invalid or expired link", message="This link is invalid or has expired."), 403

    try:
        data = get_submission_data(submission_id)
        if data.get("status") not in ("pending", None):
            return render_template("action_message.html", title="Already processed", message=f"This request was already {data.get('status')}."), 200

        update_submission_status(submission_id, "denied")
        _executor.submit(_deny_background, submission_id, data)
        return render_template("denied.html"), 200

    except Exception as e:
        logger.error("Deny error for %s: %s", submission_id, e)
        return render_template("action_message.html", title="Error", message=f"Something went wrong: {e}"), 500


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat(), "service": "webapp"})
