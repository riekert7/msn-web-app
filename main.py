import atexit
import json
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import wraps

import sentry_sdk
from authlib.integrations.flask_client import OAuth
from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from sentry_sdk.integrations.flask import FlaskIntegration

from drive import share_study_materials
from email_utils import (
    send_student_approved_email,
    send_student_denied_email,
    send_submission_emails_in_background,
    verify_approval_token,
)
from sheets import get_all_submissions, log_to_google_sheets, update_google_sheets_status
from storage import (
    get_file_from_gcs,
    get_submission_data,
    store_file_in_gcs,
    store_submission_metadata,
    update_submission_status,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[FlaskIntegration()],
    traces_sample_rate=0.2,
    send_default_pii=False,
    environment=os.environ.get("FLASK_ENV", "production"),
)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

oauth = OAuth(app)
google_oauth = oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

_executor = ThreadPoolExecutor(max_workers=4)
atexit.register(_executor.shutdown, wait=True)

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _admin_emails() -> list[str]:
    return [e.strip().lower() for e in os.environ.get("ADMINISTRATORS", "").split(",") if e.strip()]


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        email = session.get("admin_email")
        if not email:
            return redirect(url_for("admin_login"))
        if email not in _admin_emails():
            session.clear()
            return render_template("action_message.html", title="Access denied", message="Your account is not authorised as an admin."), 403
        return f(*args, **kwargs)
    return decorated


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
            "timestamp": request.form.get("timestamp", datetime.now(UTC).isoformat()),
            "status": "pending",
            "gcs_file_path": None,
        }

        logger.info("Processing submission: %s", submission_id)
        gcs_path = store_file_in_gcs(file_data, file.filename, submission_id, file.content_type)
        submission_data["gcs_file_path"] = gcs_path
        store_submission_metadata(submission_data)
        log_to_google_sheets(submission_data)

        _executor.submit(send_submission_emails_in_background, submission_data)

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
# Admin approve / deny (email link flow)
# ---------------------------------------------------------------------------

def _approve_background(submission_id: str, data: dict) -> None:
    try:
        shared = share_study_materials(data["email"], data["module"], data["chapters"])
        update_submission_status(submission_id, "approved", {"shared_files": shared})
        update_google_sheets_status(submission_id, "approved")
        send_student_approved_email(data, shared)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.error("[APPROVE] Background error for %s: %s", submission_id, e)


@app.get("/approve/<submission_id>")
def approve(submission_id: str):
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
    try:
        update_google_sheets_status(submission_id, "denied")
        send_student_denied_email(data)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.error("[DENY] Background error for %s: %s", submission_id, e)


@app.get("/deny/<submission_id>")
def deny(submission_id: str):
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
# View proof of payment (token-protected, used in admin email)
# ---------------------------------------------------------------------------

@app.get("/view-payment/<submission_id>")
def view_payment(submission_id: str):
    """Token-protected view used in admin notification emails."""
    token = request.args.get("token")
    if not verify_approval_token(submission_id, token or ""):
        return "Invalid or expired link", 403
    return _serve_payment_file(submission_id)


@app.get("/admin/view-payment/<submission_id>")
@require_admin
def admin_view_payment(submission_id: str):
    """Session-protected view used from the admin dashboard."""
    return _serve_payment_file(submission_id)


def _serve_payment_file(submission_id: str) -> Response:
    try:
        data = get_submission_data(submission_id)
        gcs_path = data.get("gcs_file_path")
        if not gcs_path:
            return "No proof of payment on file", 404
        file_data, content_type = get_file_from_gcs(gcs_path)
        filename = data.get("file_name", "proof")
        return Response(
            file_data,
            mimetype=content_type,
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("view_payment error for %s: %s", submission_id, e)
        return "Error retrieving file", 500


# ---------------------------------------------------------------------------
# Admin dashboard (Google SSO)
# ---------------------------------------------------------------------------

@app.get("/admin/login")
def admin_login():
    return render_template("admin_login.html")


@app.get("/admin/auth/google")
def admin_auth_google():
    base = os.environ.get("BASE_URL", "").rstrip("/")
    callback_url = f"{base}/admin/callback" if base else url_for("admin_callback", _external=True)
    return google_oauth.authorize_redirect(callback_url)


@app.get("/admin/callback")
def admin_callback():
    try:
        token = google_oauth.authorize_access_token()
        user_info = token.get("userinfo") or google_oauth.userinfo()
        email = (user_info.get("email") or "").lower()
        if not email:
            return render_template("action_message.html", title="Login failed", message="Could not retrieve your email from Google."), 400
        if email not in _admin_emails():
            return render_template("action_message.html", title="Access denied", message="Your Google account is not authorised as an admin."), 403
        session.permanent = True
        session["admin_email"] = email
        session["admin_name"] = user_info.get("name", email)
        return redirect(url_for("admin_submissions"))
    except Exception as e:
        logger.error("OAuth callback error: %s", e)
        return render_template("action_message.html", title="Login error", message=f"Something went wrong during login: {e}"), 500


@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/admin")
@require_admin
def admin_dashboard():
    return redirect(url_for("admin_submissions"))


@app.get("/admin/submissions")
@require_admin
def admin_submissions():
    submissions = get_all_submissions()
    pending_count = sum(1 for s in submissions if (s.get("status") or "").lower() == "pending")
    return render_template(
        "admin_submissions.html",
        submissions=submissions,
        pending_count=pending_count,
        admin_email=session.get("admin_email"),
        admin_name=session.get("admin_name"),
        msg=request.args.get("msg"),
        err=request.args.get("err"),
        active_tab="submissions",
    )


@app.get("/admin/share")
@require_admin
def admin_share_page():
    return render_template(
        "admin_share.html",
        pending_count=None,
        admin_email=session.get("admin_email"),
        admin_name=session.get("admin_name"),
        msg=request.args.get("msg"),
        err=request.args.get("err"),
        active_tab="share",
    )


@app.post("/admin/deny/<submission_id>")
@require_admin
def admin_deny(submission_id: str):
    try:
        data = get_submission_data(submission_id)
        update_submission_status(submission_id, "denied")
        update_google_sheets_status(submission_id, "denied")
        send_student_denied_email(data)
        logger.info("Admin denied %s for %s", submission_id, data["email"])
        return jsonify({"ok": True})
    except Exception as e:
        logger.error("Deny error for %s: %s", submission_id, e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/admin/reshare/<submission_id>")
@require_admin
def admin_reshare(submission_id: str):
    try:
        data = get_submission_data(submission_id)
        shared = share_study_materials(data["email"], data["module"], data["chapters"])
        send_student_approved_email(data, shared)
        update_submission_status(submission_id, "approved", {"shared_files": shared})
        update_google_sheets_status(submission_id, "approved")
        logger.info("Admin reshared %s for %s", submission_id, data["email"])
        return jsonify({"ok": True, "shared_count": len(shared)})
    except Exception as e:
        logger.error("Reshare error for %s: %s", submission_id, e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/admin/share")
@require_admin
def admin_share():
    try:
        first_name = request.form["firstName"].strip()
        last_name = request.form["lastName"].strip()
        email = request.form["email"].strip().lower()
        phone = request.form.get("phone", "").strip()
        module = request.form["module"]
        chapters = [c.strip() for c in request.form.getlist("chapters") if c.strip()]
        total_cost = int(request.form.get("totalCost", 0))

        if not all((first_name, last_name, email, module, chapters)):
            return redirect(url_for("admin_share_page", err="Missing required fields"))

        submission_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        submission_data = {
            "submission_id": submission_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "module": module,
            "chapters": chapters,
            "total_cost": total_cost,
            "file_name": None,
            "file_size": 0,
            "file_mime_type": None,
            "timestamp": now,
            "status": "approved",
            "gcs_file_path": None,
            "admin_share": True,
        }

        store_submission_metadata(submission_data)
        log_to_google_sheets(submission_data)

        shared = share_study_materials(email, module, chapters)
        send_student_approved_email(submission_data, shared)
        update_google_sheets_status(submission_id, "approved")

        logger.info("Admin direct-shared %s %s chapters with %s", module, chapters, email)
        return redirect(url_for("admin_share_page", msg=f"Shared {len(shared)} file(s) with {email}"))

    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.error("Admin share error: %s", e)
        return redirect(url_for("admin_share_page", err=str(e)))


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy", "timestamp": datetime.now(UTC).isoformat(), "service": "webapp"})


# ---------------------------------------------------------------------------
# Debug endpoints
# ---------------------------------------------------------------------------

@app.get("/debug-sentry")
def debug_sentry():
    1 / 0


@app.get("/debug-smtp")
def debug_smtp():
    import socket

    host = os.environ.get("SMTP_HOST", "")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME", "")
    password = os.environ.get("SMTP_PASSWORD", "")

    result = {
        "smtp_host": host or None,
        "smtp_port": port,
        "smtp_username": username or None,
        "tcp_connect": None,
        "starttls": None,
        "cert_subject": None,
        "cert_expiry": None,
        "cert_expired": None,
        "login": None,
        "error": None,
    }

    if not host:
        result["error"] = "SMTP_HOST not set"
        return jsonify(result), 500

    try:
        import smtplib
        import ssl as _ssl
        with socket.create_connection((host, port), timeout=10):
            result["tcp_connect"] = True
    except Exception as e:
        result["tcp_connect"] = False
        result["error"] = f"TCP connect failed: {e}"
        return jsonify(result), 500

    import smtplib
    import ssl as _ssl

    ctx = _ssl.create_default_context()
    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls(context=ctx)
            result["starttls"] = True
            cert = server.sock.getpeercert()
            if cert:
                not_after = cert.get("notAfter")
                result["cert_subject"] = dict(x[0] for x in cert.get("subject", []))
                result["cert_expiry"] = not_after
                if not_after:
                    expiry_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
                    result["cert_expired"] = expiry_dt < datetime.now(UTC)
    except _ssl.SSLCertVerificationError as e:
        result["starttls"] = False
        result["error"] = f"SSL cert verification failed: {e}"
        ctx_noverify = _ssl.create_default_context()
        ctx_noverify.check_hostname = False
        ctx_noverify.verify_mode = _ssl.CERT_NONE
        try:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls(context=ctx_noverify)
                cert = server.sock.getpeercert()
                if cert:
                    not_after = cert.get("notAfter")
                    result["cert_subject"] = dict(x[0] for x in cert.get("subject", []))
                    result["cert_expiry"] = not_after
                    if not_after:
                        expiry_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
                        result["cert_expired"] = expiry_dt < datetime.now(UTC)
        except Exception:  # nosec B110
            pass
        return jsonify(result), 500
    except Exception as e:
        result["starttls"] = False
        result["error"] = f"STARTTLS failed: {e}"
        return jsonify(result), 500

    if username and password:
        try:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls(context=ctx)
                server.login(username, password)
                result["login"] = True
        except Exception as e:
            result["login"] = False
            result["error"] = f"Login failed: {e}"
            return jsonify(result), 500

    return jsonify(result)
