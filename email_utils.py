import hashlib
import hmac
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import sentry_sdk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token helpers (here to avoid a circular import with main.py)
# ---------------------------------------------------------------------------

def approval_token(submission_id: str) -> str:
    """HMAC-SHA256 token for approve/deny links — prevents forgery."""
    secret = os.environ.get("APPROVAL_SECRET", "").encode()
    return hmac.new(secret, submission_id.encode(), hashlib.sha256).hexdigest()


def verify_approval_token(submission_id: str, token: str) -> bool:
    return bool(token) and hmac.compare_digest(approval_token(submission_id), token)

_SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "info@miyastudynotes.co.za")
_WHATSAPP_URL = "https://wa.me/27793688500"


def _phone_to_whatsapp(phone: str, country_code: str = "27") -> str:
    """Normalise a South African phone number for wa.me (e.g. 0793688500 to 27793688500)."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if not digits:
        return ""
    if digits.startswith("0"):
        digits = country_code + digits[1:]
    elif not digits.startswith(country_code):
        digits = country_code + digits
    return digits


def _contact_block_html() -> str:
    """Reusable 'Need help?' section for student emails."""
    return (
        f'<p style="margin-top:24px;margin-bottom:8px;font-size:15px;color:#495057;">Need help?</p>'
        f'<p style="margin:0 0 8px 0;">'
        f'<a href="{_WHATSAPP_URL}" style="display:inline-block;background:#25D366;color:#fff;'
        f'padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">'
        f'WhatsApp me</a></p>'
        f'<p style="margin:0;font-size:14px;color:#6c757d;">'
        f'Or email <a href="mailto:{_SUPPORT_EMAIL}" style="color:#667eea;text-decoration:none;">'
        f'{_SUPPORT_EMAIL}</a></p>'
    )


def _smtp_config() -> tuple:
    """Return (host, port, username, password, from_email) or raise if not configured."""
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("FROM_EMAIL")
    return host, port, username, password, from_email


def _send_email(to: str, subject: str, text: str, html: str | None = None, reply_to: str | None = None) -> bool:
    host, port, username, password, from_email = _smtp_config()
    if not all((host, username, password, from_email)):
        logger.warning("SMTP not configured — set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL in .env")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.attach(MIMEText(text, "plain"))
        if html:
            msg.attach(MIMEText(html, "html"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port) as server:
            server.starttls(context=ctx)
            server.login(username, password)
            server.sendmail(from_email, [to], msg.as_string())
        logger.info("Sent to %s: %s", to, subject[:60])
        return True
    except Exception as e:
        logger.error("Failed to %s: %s", to, e)
        return False


# ---------------------------------------------------------------------------
# Public email functions
# ---------------------------------------------------------------------------

def send_admin_new_submission_email(submission_data: dict) -> bool:
    """Send admin a plain notification that a new submission arrived. Review via the dashboard."""
    admin_email = os.environ.get("ADMIN_EMAIL")
    base_url = (os.environ.get("BASE_URL") or "http://localhost:5000").rstrip("/")
    if not admin_email:
        logger.warning("ADMIN_EMAIL not set — skipping admin notification")
        return False

    student_email = submission_data["email"]
    wa = _phone_to_whatsapp(submission_data.get("phone", ""))
    wa_url = f"https://wa.me/{wa}" if wa else ""
    dashboard_url = f"{base_url}/admin/submissions?status=pending"

    subject = "MiyaStudyNotes: New study material request"
    text = (
        f"New submission received.\n\n"
        f"Name: {submission_data['first_name']} {submission_data['last_name']}\n"
        f"Email: {student_email}\n"
        f"Phone: {submission_data.get('phone', '')}\n"
        f"Module: {submission_data['module']}\n"
        f"Chapters: {', '.join(submission_data['chapters'])}\n"
        f"Total: R{submission_data['total_cost']}\n"
        + (f"WhatsApp: {wa_url}\n" if wa_url else "")
        + f"\nReview and approve/deny at: {dashboard_url}\n"
    )
    html = (
        f"<p>New submission received.</p>"
        f"<p><strong>Name:</strong> {submission_data['first_name']} {submission_data['last_name']}<br>"
        f"<strong>Email:</strong> {student_email}<br>"
        f"<strong>Phone:</strong> {submission_data.get('phone', '')}<br>"
        f"<strong>Module:</strong> {submission_data['module']}<br>"
        f"<strong>Chapters:</strong> {', '.join(submission_data['chapters'])}<br>"
        f"<strong>Total:</strong> R{submission_data['total_cost']}</p>"
        + (f'<p><a href="{wa_url}" style="color:#25D366;">WhatsApp student</a></p>' if wa_url else "")
        + f'<p><a href="{dashboard_url}" style="display:inline-block;background:#667eea;color:white;'
        f'padding:12px 24px;text-decoration:none;border-radius:6px;">Review submissions</a></p>'
    )
    return _send_email(admin_email, subject, text, html=html)


def send_student_confirmation_email(submission_data: dict) -> bool:
    """Confirm to the student that their request was received."""
    name = submission_data.get("first_name", "there")
    module = submission_data["module"]
    subject = "I received your study notes request"
    text = (
        f"Hi {name},\n\n"
        f"I received your request for {module} (R{submission_data['total_cost']}). "
        f"I'll review your payment and share the notes via Google Drive once approved.\n\n"
        f"WhatsApp: {_WHATSAPP_URL}\nEmail: {_SUPPORT_EMAIL}\n\nMiya"
    )
    html = (
        f'<div style="font-family:sans-serif;max-width:520px;color:#333;">'
        f"<p>Hi {name},</p>"
        f"<p>I received your request for <strong>{module}</strong> (R{submission_data['total_cost']}). "
        f"I'll review your payment and share the notes via Google Drive once approved.</p>"
        f"{_contact_block_html()}"
        f'<p style="margin-top:24px;font-size:14px;color:#6c757d;">Miya</p></div>'
    )
    return _send_email(submission_data["email"], subject, text, html=html, reply_to=_SUPPORT_EMAIL)


def send_student_approved_email(submission_data: dict, shared_files: list) -> bool:
    """Tell the student their notes are ready and provide Drive links."""
    name = submission_data.get("first_name", "there")
    module = submission_data["module"]
    links_text = "\n".join(
        f"  - {s['name']}: https://drive.google.com/file/d/{s['id']}/view" for s in shared_files
    )
    links_html = "".join(
        f'<li style="margin:6px 0;"><a href="https://drive.google.com/file/d/{s["id"]}/view" style="color:#667eea;">{s["name"]}</a></li>'
        for s in shared_files
    )
    subject = f"Your {module} notes are ready"
    text = (
        f"Hi {name},\n\nYour {module} notes are ready. "
        f"I've shared them with you on Google Drive.\n\n"
        f"Open Google Drive to Shared with me, or use these links:\n\n{links_text}\n\n"
        f"WhatsApp: {_WHATSAPP_URL}\nEmail: {_SUPPORT_EMAIL}\n\nMiya"
    )
    html = (
        f'<div style="font-family:sans-serif;max-width:520px;color:#333;">'
        f"<p>Hi {name},</p>"
        f"<p>Your <strong>{module}</strong> notes are ready. I've shared them with you on Google Drive.</p>"
        f"<p>Open <strong>Google Drive to Shared with me</strong>, or use these links:</p>"
        f'<ul style="margin:12px 0;padding-left:20px;">{links_html}</ul>'
        f"{_contact_block_html()}"
        f'<p style="margin-top:24px;font-size:14px;color:#6c757d;">Miya</p></div>'
    )
    return _send_email(submission_data["email"], subject, text, html=html, reply_to=_SUPPORT_EMAIL)


def send_student_denied_email(submission_data: dict) -> bool:
    """Tell the student their request was not approved."""
    name = submission_data.get("first_name", "there")
    module = submission_data["module"]
    subject = "Update on your study notes request"
    text = (
        f"Hi {name},\n\nI couldn't approve your request for {module} at this time. "
        f"If you have questions, get in touch:\n\n"
        f"WhatsApp: {_WHATSAPP_URL}\nEmail: {_SUPPORT_EMAIL}\n\nMiya"
    )
    html = (
        f'<div style="font-family:sans-serif;max-width:520px;color:#333;">'
        f"<p>Hi {name},</p>"
        f"<p>I couldn't approve your request for <strong>{module}</strong> at this time.</p>"
        f"{_contact_block_html()}"
        f'<p style="margin-top:24px;font-size:14px;color:#6c757d;">Miya</p></div>'
    )
    return _send_email(submission_data["email"], subject, text, html=html, reply_to=_SUPPORT_EMAIL)


def send_submission_emails_in_background(submission_data: dict) -> None:
    """Run in thread pool: admin notification + student confirmation."""
    sid = submission_data.get("submission_id", "?")
    logger.info("Background email task started for %s", sid)
    try:
        ok_admin = send_admin_new_submission_email(submission_data)
        logger.info("Admin email: %s", "OK" if ok_admin else "FAILED")
        ok_student = send_student_confirmation_email(submission_data)
        logger.info("Student confirmation: %s", "OK" if ok_student else "FAILED")
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.error("Background email error for %s: %s", sid, e)
