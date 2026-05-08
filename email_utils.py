import os
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from auth import approval_token

_SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "info@miyastudynotes.co.za")
_WHATSAPP_URL = "https://wa.me/27793688500"


def _log(msg: str) -> None:
    print(f"[EMAIL] {msg}")


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
        _log("SMTP not configured — set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL in .env")
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
        _log(f"Sent to {to}: {subject[:60]}")
        return True
    except Exception as e:
        _log(f"Failed to {to}: {e}")
        return False


def _send_email_with_attachment(
    to: str,
    subject: str,
    text: str,
    html: str | None,
    attachment_name: str,
    attachment_data: bytes,
    attachment_mimetype: str,
) -> bool:
    host, port, username, password, from_email = _smtp_config()
    if not all((host, username, password, from_email)):
        _log("SMTP not configured (attachment email)")
        return False
    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to
        body = MIMEMultipart("alternative")
        body.attach(MIMEText(text, "plain"))
        if html:
            body.attach(MIMEText(html, "html"))
        msg.attach(body)
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment_data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=(attachment_name or "attachment"))
        msg.attach(part)
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port) as server:
            server.starttls(context=ctx)
            server.login(username, password)
            server.sendmail(from_email, [to], msg.as_string())
        _log(f"Sent (attachment) to {to}: {subject[:60]}")
        return True
    except Exception as e:
        _log(f"Failed (attachment) to {to}: {e}")
        return False


# ---------------------------------------------------------------------------
# Public email functions
# ---------------------------------------------------------------------------

def send_admin_new_submission_email(submission_data: dict, file_data: bytes, filename: str, content_type: str) -> bool:
    """Send admin notification with approve/deny links and proof-of-payment attached."""
    admin_email = os.environ.get("ADMIN_EMAIL")
    base_url = (os.environ.get("BASE_URL") or "http://localhost:5000").rstrip("/")
    if not admin_email:
        _log("ADMIN_EMAIL not set — skipping admin notification")
        return False
    if not os.environ.get("APPROVAL_SECRET"):
        _log("APPROVAL_SECRET not set — approve/deny links will not work")
        return False

    sid = submission_data["submission_id"]
    token = approval_token(sid)
    approve_url = f"{base_url}/approve/{sid}?token={token}"
    deny_url = f"{base_url}/deny/{sid}?token={token}"

    student_email = submission_data["email"]
    wa = _phone_to_whatsapp(submission_data.get("phone", ""))
    wa_url = f"https://wa.me/{wa}" if wa else ""
    reach_html = (
        f'<p><strong>Reach student:</strong> '
        f'<a href="mailto:{student_email}" style="color:#667eea;">Email</a>'
        + (f' | <a href="{wa_url}" style="color:#25D366;">WhatsApp</a>' if wa_url else "")
        + "</p>"
    )

    subject = "MiyaStudyNotes: New study material request – approve or deny"
    text = (
        f"New submission received.\n\n"
        f"Submission ID: {sid}\n"
        f"Name: {submission_data['first_name']} {submission_data['last_name']}\n"
        f"Email: {student_email}\n"
        f"Phone: {submission_data.get('phone', '')}\n"
        f"Module: {submission_data['module']}\n"
        f"Chapters: {', '.join(submission_data['chapters'])}\n"
        f"Total cost: R{submission_data['total_cost']}\n"
        f"Payment file: {filename} (attached)\n\n"
        f"Reach student: Email {student_email}"
        + (f" | WhatsApp {wa_url}" if wa_url else "")
        + f"\n\nApprove: {approve_url}\nDeny: {deny_url}\n"
    )
    html = (
        f"<p>New submission received.</p>"
        f"<p><strong>Name:</strong> {submission_data['first_name']} {submission_data['last_name']}<br>"
        f"<strong>Email:</strong> {student_email}<br>"
        f"<strong>Phone:</strong> {submission_data.get('phone', '')}<br>"
        f"<strong>Module:</strong> {submission_data['module']}<br>"
        f"<strong>Chapters:</strong> {', '.join(submission_data['chapters'])}<br>"
        f"<strong>Total cost:</strong> R{submission_data['total_cost']}</p>"
        f"<p>Proof of payment is attached.</p>"
        f"{reach_html}"
        f'<p><a href="{approve_url}" style="display:inline-block;background:#28a745;color:white;'
        f'padding:12px 24px;text-decoration:none;border-radius:6px;margin-right:10px;">Approve</a>'
        f'<a href="{deny_url}" style="display:inline-block;background:#dc3545;color:white;'
        f'padding:12px 24px;text-decoration:none;border-radius:6px;">Deny</a></p>'
    )
    return _send_email_with_attachment(admin_email, subject, text, html, filename or "proof", file_data, content_type or "application/octet-stream")


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


def send_submission_emails_in_background(submission_data: dict, file_data: bytes, filename: str, content_type: str) -> None:
    """Run in thread pool: admin email with attachment + student confirmation."""
    sid = submission_data.get("submission_id", "?")
    _log(f"Background email task started for {sid}")
    try:
        ok_admin = send_admin_new_submission_email(submission_data, file_data, filename, content_type or "application/octet-stream")
        _log(f"Admin email: {'OK' if ok_admin else 'FAILED'}")
        ok_student = send_student_confirmation_email(submission_data)
        _log(f"Student confirmation: {'OK' if ok_student else 'FAILED'}")
    except Exception as e:
        _log(f"Background email error for {sid}: {e}")
