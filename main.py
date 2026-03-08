import hmac
import hashlib
import os
import json
import smtplib
import ssl
import threading
import uuid
from datetime import datetime, timezone
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from flask import Flask, request, jsonify, render_template
from google.cloud import storage
from google.auth import default
from googleapiclient.discovery import build
from werkzeug.utils import secure_filename


app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
)

# Initialize Google Cloud Storage
storage_client = storage.Client()
bucket_name = os.environ.get("GCS_BUCKET_NAME", "miyastudynotes-temp")

# Allowed file types and size limit
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def allowed_file(filename: str) -> bool:
    """Check if file type is allowed."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def log_to_google_sheets(submission_data: dict) -> bool:
    """Log submission data to Google Sheets."""
    sheets_id = os.environ.get("GOOGLE_SHEETS_ID")

    if not sheets_id:
        print("Google Sheets ID not configured, skipping sheets logging")
        return False

    try:
        creds, _ = default(
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=creds)

        timestamp = datetime.fromisoformat(
            submission_data["timestamp"].replace("Z", "+00:00")
        )
        row_data = [
            timestamp.isoformat(),  # A: Timestamp
            submission_data["submission_id"],  # B: Submission ID
            f"{submission_data['first_name']} {submission_data['last_name']}",  # C
            submission_data["email"],  # D: Email
            submission_data["phone"],  # E: Phone
            submission_data["module"],  # F: Module
            ", ".join(submission_data["chapters"]),  # G: Chapters
            submission_data["total_cost"],  # H: Total Cost
            submission_data["file_name"],  # I: Payment File
            f"{submission_data['file_size']}MB",  # J: File Size
            submission_data["status"],  # K: Status
            "",  # L: Approval Date (empty initially)
            "",  # M: Admin Notes (empty initially)
        ]

        body = {"values": [row_data]}
        service.spreadsheets().values().append(
            spreadsheetId=sheets_id,
            range="Submissions!A:M",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()

        print("Successfully logged submission to Google Sheets")
        return True
    except Exception as e:
        print(f"Failed to log to Google Sheets: {e}")
        return False


def _approval_token(submission_id: str) -> str:
    """Generate HMAC token for approve/deny links so they cannot be forged."""
    secret = os.environ.get("APPROVAL_SECRET", "").encode()
    return hmac.new(secret, submission_id.encode(), hashlib.sha256).hexdigest()


def _verify_approval_token(submission_id: str, token: str) -> bool:
    return token and hmac.compare_digest(_approval_token(submission_id), token)


def _email_debug(msg: str) -> None:
    """Print email debug line (always on for email sending)."""
    print(f"[EMAIL] {msg}")


def _send_smtp_email(to_email: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    """Send a single email via SMTP (xneelo or any SMTP server)."""
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("FROM_EMAIL")

    if not all((host, username, password, from_email)):
        _email_debug("SMTP not configured: set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL in .env")
        return False

    try:
        _email_debug(f"Connecting to {host}:{port} (STARTTLS)")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        context = ssl.create_default_context()
        with smtplib.SMTP(host, port) as server:
            _email_debug("Starting TLS")
            server.starttls(context=context)
            _email_debug(f"Logging in as {username}")
            server.login(username, password)
            _email_debug(f"Sending to {to_email}: {subject[:50]}...")
            server.sendmail(from_email, [to_email], msg.as_string())
        _email_debug(f"Sent OK to {to_email}: {subject}")
        return True
    except Exception as e:
        _email_debug(f"Failed to send to {to_email}: {e}")
        return False


def _send_smtp_email_with_attachment(
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None,
    attachment_filename: str,
    attachment_data: bytes,
    attachment_mimetype: str,
) -> bool:
    """Send email via SMTP with one file attachment."""
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("FROM_EMAIL")

    if not all((host, username, password, from_email)):
        _email_debug("SMTP not configured (attachment email)")
        return False

    try:
        _email_debug(f"Connecting to {host}:{port} for email with attachment to {to_email}")
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email

        part_body = MIMEMultipart("alternative")
        part_body.attach(MIMEText(body_text, "plain"))
        if body_html:
            part_body.attach(MIMEText(body_html, "html"))
        msg.attach(part_body)

        part_file = MIMEBase("application", "octet-stream")
        part_file.set_payload(attachment_data)
        encoders.encode_base64(part_file)
        part_file.add_header(
            "Content-Disposition",
            "attachment",
            filename=(attachment_filename or "attachment"),
        )
        msg.attach(part_file)
        _email_debug(f"Attachment: {attachment_filename} ({len(attachment_data)} bytes)")

        context = ssl.create_default_context()
        with smtplib.SMTP(host, port) as server:
            _email_debug("Starting TLS")
            server.starttls(context=context)
            _email_debug(f"Logging in as {username}")
            server.login(username, password)
            _email_debug(f"Sending to {to_email}: {subject[:50]}...")
            server.sendmail(from_email, [to_email], msg.as_string())
        _email_debug(f"Sent OK (with attachment) to {to_email}: {subject}")
        return True
    except Exception as e:
        _email_debug(f"Failed to send to {to_email}: {e}")
        return False


def send_admin_new_submission_email(
    submission_data: dict,
    file_data: bytes,
    filename: str,
    content_type: str,
) -> bool:
    """Notify the admin by email: body includes Approve/Deny links, and the PoP file is attached."""
    admin_email = os.environ.get("ADMIN_EMAIL")
    base_url = (os.environ.get("BASE_URL") or "http://localhost:5000").rstrip("/")
    if not admin_email:
        print("ADMIN_EMAIL not set in .env, skipping admin notification")
        return False
    if not os.environ.get("APPROVAL_SECRET"):
        print("APPROVAL_SECRET not set in .env; approve/deny links will not work")
        return False

    sid = submission_data["submission_id"]
    token = _approval_token(sid)
    approve_url = f"{base_url}/approve/{sid}?token={token}"
    deny_url = f"{base_url}/deny/{sid}?token={token}"

    subject = "MiyaStudyNotes: New study material request – approve or deny"
    body_text = (
        f"New submission received.\n\n"
        f"Submission ID: {sid}\n"
        f"Name: {submission_data['first_name']} {submission_data['last_name']}\n"
        f"Email: {submission_data['email']}\n"
        f"Phone: {submission_data['phone']}\n"
        f"Module: {submission_data['module']}\n"
        f"Chapters: {', '.join(submission_data['chapters'])}\n"
        f"Total cost: R{submission_data['total_cost']}\n"
        f"Payment file: {filename} (attached)\n\n"
        f"Approve: {approve_url}\n"
        f"Deny: {deny_url}\n"
    )
    body_html = (
        f"<p>New submission received.</p>"
        f"<p><strong>Name:</strong> {submission_data['first_name']} {submission_data['last_name']}<br>"
        f"<strong>Email:</strong> {submission_data['email']}<br>"
        f"<strong>Phone:</strong> {submission_data['phone']}<br>"
        f"<strong>Module:</strong> {submission_data['module']}<br>"
        f"<strong>Chapters:</strong> {', '.join(submission_data['chapters'])}<br>"
        f"<strong>Total cost:</strong> R{submission_data['total_cost']}</p>"
        f"<p>Proof of payment is attached.</p>"
        f"<p>"
        f'<a href="{approve_url}" style="display:inline-block;background:#28a745;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;margin-right:10px;">Approve</a>'
        f'<a href="{deny_url}" style="display:inline-block;background:#dc3545;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;">Deny</a>'
        f"</p>"
    )

    return _send_smtp_email_with_attachment(
        admin_email,
        subject,
        body_text,
        body_html,
        filename or "proof",
        file_data,
        content_type or "application/octet-stream",
    )


def _send_submission_emails_in_background(
    submission_data: dict,
    file_data: bytes,
    filename: str,
    content_type: str,
) -> None:
    """Run in a thread: send admin email (with attachment) and student confirmation. Logs and catches errors."""
    sid = submission_data.get("submission_id", "?")
    _email_debug(f"Background email task started for submission {sid}")
    try:
        _email_debug("Sending admin email (with PoP attachment and Approve/Deny links)...")
        ok_admin = send_admin_new_submission_email(
            submission_data, file_data, filename, content_type or "application/octet-stream"
        )
        _email_debug(f"Admin email: {'OK' if ok_admin else 'FAILED'}")

        _email_debug("Sending student confirmation email...")
        ok_student = send_student_confirmation_email(submission_data)
        _email_debug(f"Student confirmation email: {'OK' if ok_student else 'FAILED'}")

        _email_debug(f"Background email task finished for {sid}")
    except Exception as e:
        _email_debug(f"Background email task error for {sid}: {e}")


def send_student_confirmation_email(submission_data: dict) -> bool:
    """Send the student a confirmation email that their request was received."""
    to_email = submission_data["email"]
    name = f"{submission_data['first_name']} {submission_data['last_name']}"
    subject = "MiyaStudyNotes: We received your request"
    body = (
        f"Hi {name},\n\n"
        f"We've received your study notes request.\n\n"
        f"Module: {submission_data['module']}\n"
        f"Chapters: {', '.join(submission_data['chapters'])}\n"
        f"Total: R{submission_data['total_cost']}\n\n"
        f"We'll review your proof of payment and send you access to the notes via Google Drive once approved.\n\n"
        f"Thanks,\nMiya Study Notes"
    )
    return _send_smtp_email(to_email, subject, body)


def store_file_in_gcs(file_data: bytes, filename: str, submission_id: str, content_type: str) -> str:
    """Store uploaded file in Google Cloud Storage."""
    try:
        bucket = storage_client.bucket(bucket_name)
        sanitized_filename = secure_filename(filename)
        gcs_filename = f"submissions/{submission_id}/{sanitized_filename}"

        blob = bucket.blob(gcs_filename)
        blob.metadata = {
            "submission_id": submission_id,
            "original_name": filename,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }

        blob.upload_from_string(file_data, content_type=content_type)

        print(f"File uploaded successfully: {gcs_filename}")
        return gcs_filename
    except Exception as e:
        print(f"Failed to store file in GCS: {e}")
        raise


def store_submission_metadata(submission_data: dict) -> str:
    """Store submission metadata in GCS."""
    try:
        bucket = storage_client.bucket(bucket_name)
        metadata_filename = f"submissions/{submission_data['submission_id']}/metadata.json"

        blob = bucket.blob(metadata_filename)
        blob.upload_from_string(
            json.dumps(submission_data, indent=2),
            content_type="application/json",
        )

        print("Submission metadata stored successfully")
        return metadata_filename
    except Exception as e:
        print(f"Failed to store submission metadata: {e}")
        raise


def get_submission_data(submission_id: str) -> dict:
    """Load submission metadata from GCS."""
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(f"submissions/{submission_id}/metadata.json")
    return json.loads(blob.download_as_text())


def _get_drive_service():
    """Initialize Google Drive API (service account)."""
    creds, _ = default(scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds)


def _find_chapter_files(drive, parent_folder_id: str, module: str, chapter_number: str) -> list:
    """Find Drive files for a chapter by name pattern: '<MODULE> - Chapter <N>'."""
    if not parent_folder_id:
        return []
    pattern = f"{module} - Chapter {chapter_number}"
    q = f"parents in '{parent_folder_id}' and name contains '{pattern}' and trashed=false"
    res = drive.files().list(
        q=q,
        fields="files(id, name)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    ).execute()
    return res.get("files", [])


def share_study_materials(email: str, module: str, chapters: list) -> list:
    """Share requested chapter files from Drive with the user. Returns list of shared file info."""
    from googleapiclient.errors import HttpError

    folder_ids = {
        "EKN110": os.environ.get("EKN110_FOLDER_ID"),
        "EKN120": os.environ.get("EKN120_FOLDER_ID"),
        "EKN214": os.environ.get("EKN214_FOLDER_ID"),
    }
    parent_id = folder_ids.get(module)
    if not parent_id:
        raise ValueError(f"No folder mapping for module: {module}")

    drive = _get_drive_service()
    shared = []
    for chapter in chapters:
        try:
            num = chapter.split("-")[1]
            for f in _find_chapter_files(drive, parent_id, module, num):
                perm = {"role": "reader", "type": "user", "emailAddress": email}
                try:
                    drive.permissions().create(
                        fileId=f["id"],
                        body=perm,
                        sendNotificationEmails=False,
                        supportsAllDrives=True,
                    ).execute()
                    shared.append({"id": f["id"], "name": f["name"], "chapter": num})
                except HttpError as e:
                    print(f"Drive permission error for {f['id']}: {e}")
        except Exception as e:
            print(f"Share chapter {chapter}: {e}")
    return shared


def update_submission_status(submission_id: str, status: str, extra: dict | None = None) -> dict:
    """Update metadata in GCS and optionally Sheets."""
    data = get_submission_data(submission_id)
    data["status"] = status
    data["processed_at"] = datetime.now(timezone.utc).isoformat()
    if extra:
        data["admin_action"] = extra
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(f"submissions/{submission_id}/metadata.json")
    blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")
    return data


def update_google_sheets_status(submission_id: str, status: str, admin_action: dict | None = None) -> bool:
    """Update status and approval date in the Submissions sheet."""
    sheets_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not sheets_id:
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
            return False
        now = datetime.now(timezone.utc).isoformat()
        service.spreadsheets().values().update(
            spreadsheetId=sheets_id,
            range=f"Submissions!K{row_index}",
            valueInputOption="RAW",
            body={"values": [[status]]},
        ).execute()
        service.spreadsheets().values().update(
            spreadsheetId=sheets_id,
            range=f"Submissions!L{row_index}",
            valueInputOption="RAW",
            body={"values": [[now]]},
        ).execute()
        return True
    except Exception as e:
        print(f"Update sheets status: {e}")
        return False


def send_student_approved_email(submission_data: dict, shared_files: list) -> bool:
    """Email student that their request was approved and Drive was shared."""
    to = submission_data["email"]
    name = submission_data.get("first_name", "Student")
    module = submission_data["module"]
    links_text = "\n".join(
        f"  - {s['name']}: https://drive.google.com/file/d/{s['id']}/view"
        for s in shared_files
    )
    subject = f"MiyaStudyNotes: Your {module} study notes are ready"
    body = (
        f"Hi {name},\n\n"
        f"Your {module} study notes have been approved. We've shared the files with you on Google Drive.\n\n"
        f"Check your Google Drive under \"Shared with me\" for the following:\n\n{links_text}\n\n"
        f"If you don't see them, check your email for the Drive share notification and mark it as not spam.\n\n"
        f"Thanks,\nMiya Study Notes"
    )
    return _send_smtp_email(to, subject, body)


def send_student_denied_email(submission_data: dict) -> bool:
    """Email student that their request was denied."""
    to = submission_data["email"]
    name = submission_data.get("first_name", "Student")
    module = submission_data["module"]
    subject = "MiyaStudyNotes: Request update"
    body = (
        f"Hi {name},\n\n"
        f"Unfortunately your request for {module} study materials could not be approved at this time. "
        f"If you have questions, please reply to this email or contact support.\n\n"
        f"Thanks,\nMiya Study Notes"
    )
    return _send_smtp_email(to, subject, body)


@app.get("/form")
def index():
    """Render the main form."""
    return render_template("form.html")


@app.post("/submit")
def submit():
    """Handle form submission (Flask port of processSubmission)."""
    # Basic CORS-style headers (for future if needed)
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

    try:
        # Check if request has files
        if "proofOfPayment" not in request.files:
            return jsonify({"error": "Proof of payment file is required"}), 400, headers

        file = request.files["proofOfPayment"]

        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400, headers

        # Validate file
        if not allowed_file(file.filename):
            return (
                jsonify(
                    {
                        "error": "Invalid file type. Only PDF, JPG, and PNG files are allowed."
                    }
                ),
                400,
                headers,
            )

        # Check file size
        file_data = file.read()
        if len(file_data) > MAX_FILE_SIZE:
            return jsonify({"error": "File size exceeds 5MB limit"}), 400, headers

        # Reset file pointer (not strictly needed after read into file_data, but kept for consistency)
        file.seek(0)

        # Validate required form fields
        required_fields = [
            "firstName",
            "lastName",
            "email",
            "phone",
            "module",
            "chapters",
            "totalCost",
        ]
        for field in required_fields:
            if field not in request.form:
                return jsonify({"error": f"Missing required field: {field}"}), 400, headers

        # Generate unique submission ID
        submission_id = str(uuid.uuid4())

        # Parse chapters
        try:
            chapters_raw = request.form["chapters"]
            chapters = (
                json.loads(chapters_raw)
                if isinstance(chapters_raw, str)
                else [chapters_raw]
            )
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid chapters format"}), 400, headers

        # Prepare submission data
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
            "file_size": round(len(file_data) / 1024 / 1024, 2),  # Size in MB
            "file_mime_type": file.content_type,
            "timestamp": request.form.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "status": "pending",
            "gcs_file_path": None,
        }

        print(f"Processing submission: {submission_id}")

        # Store file in Google Cloud Storage
        gcs_file_path = store_file_in_gcs(
            file_data,
            file.filename,
            submission_id,
            file.content_type,
        )

        # Update submission data with file path
        submission_data["gcs_file_path"] = gcs_file_path

        # Store submission metadata
        store_submission_metadata(submission_data)

        # Log to Google Sheets
        log_to_google_sheets(submission_data)

        # Send admin + student emails in background so we return the response immediately
        thread = threading.Thread(
            target=_send_submission_emails_in_background,
            args=(
                submission_data,
                file_data,
                file.filename or "proof",
                file.content_type or "application/octet-stream",
            ),
            daemon=True,
        )
        thread.start()
        print(f"[EMAIL] Queued background email send for {submission_id}")

        # Return success response
        return (
            jsonify(
                {
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
                }
            ),
            200,
            headers,
        )
    except Exception as e:
        print(f"Error processing submission: {e}")
        return (
            jsonify(
                {
                    "error": "Internal server error",
                    "message": "Failed to process submission. Please try again.",
                }
            ),
            500,
            headers,
        )


@app.get("/approve/<submission_id>")
def approve(submission_id: str):
    """Handle approval from admin email link. Requires ?token= (HMAC of submission_id)."""
    token = request.args.get("token")
    if not _verify_approval_token(submission_id, token or ""):
        return (
            "<html><body><h1>Invalid or expired link</h1><p>This approval link is invalid or has expired.</p></body></html>",
            403,
            {"Content-Type": "text/html"},
        )
    try:
        data = get_submission_data(submission_id)
        if data.get("status") not in ("pending", None):
            return (
                f"<html><body><h1>Already processed</h1><p>This request was already {data.get('status')}.</p></body></html>",
                200,
                {"Content-Type": "text/html"},
            )
        shared = share_study_materials(data["email"], data["module"], data["chapters"])
        update_submission_status(submission_id, "approved", {"shared_files": shared})
        update_google_sheets_status(submission_id, "approved", {"shared_files": shared})
        send_student_approved_email(data, shared)
        return (
            "<html><body><h1>Request approved</h1><p>Study materials have been shared with the student and they have been emailed.</p></body></html>",
            200,
            {"Content-Type": "text/html"},
        )
    except Exception as e:
        print(f"Approval error: {e}")
        return (
            f"<html><body><h1>Error</h1><p>Something went wrong: {e}</p></body></html>",
            500,
            {"Content-Type": "text/html"},
        )


@app.get("/deny/<submission_id>")
def deny(submission_id: str):
    """Handle denial from admin email link. Requires ?token= (HMAC of submission_id)."""
    token = request.args.get("token")
    if not _verify_approval_token(submission_id, token or ""):
        return (
            "<html><body><h1>Invalid or expired link</h1><p>This link is invalid or has expired.</p></body></html>",
            403,
            {"Content-Type": "text/html"},
        )
    try:
        data = get_submission_data(submission_id)
        if data.get("status") not in ("pending", None):
            return (
                f"<html><body><h1>Already processed</h1><p>This request was already {data.get('status')}.</p></body></html>",
                200,
                {"Content-Type": "text/html"},
            )
        update_submission_status(submission_id, "denied", {})
        update_google_sheets_status(submission_id, "denied")
        send_student_denied_email(data)
        return (
            "<html><body><h1>Request denied</h1><p>The student has been notified by email.</p></body></html>",
            200,
            {"Content-Type": "text/html"},
        )
    except Exception as e:
        print(f"Deny error: {e}")
        return (
            f"<html><body><h1>Error</h1><p>Something went wrong: {e}</p></body></html>",
            500,
            {"Content-Type": "text/html"},
        )


@app.get("/healthz")
def healthz():
    """Simple health check endpoint."""
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "webapp",
        }
    )


if __name__ == "__main__":
    # For local development
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

