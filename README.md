# Miya Study Notes — Submission Portal

Web application for students to submit study note orders and for the admin to manage them.

## What it does

Students fill in a mobile-first form to order study notes for specific modules and chapters. The app handles the full lifecycle:

- Accepts proof-of-payment file uploads (PDF, JPG, PNG — max 5 MB) to **Google Cloud Storage**
- Logs each submission to a **Google Sheet** (timestamp, student details, module, chapters, cost, file)
- Emails the student a confirmation on submission and a follow-up on approval or denial
- Notifies the admin by email with a link to the dashboard when a new submission arrives

## Admin dashboard

A Google SSO-protected dashboard (restricted to emails listed in `ADMINISTRATORS`) at `/admin`:

- **Submissions table** — sortable columns, live search, status/module filters, pagination; pre-filtered pending view at `/admin/submissions?status=pending`
- **Approve / Deny** buttons per row — shares Google Drive materials and emails the student on approve; emails a denial on deny
- **Reshare** button on already-processed rows to re-send materials
- **Proof-of-payment preview** modal per row (image or PDF inline)
- **Direct Share** page (`/admin/share`) — share notes with a student without requiring a proof-of-payment upload

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python / Flask |
| Auth (admin) | Google OAuth 2.0 via Authlib |
| File storage | Google Cloud Storage |
| Submission log | Google Sheets API |
| File sharing | Google Drive API |
| Email | SMTP (Xneelo shared hosting) |
| Deployment | Google Cloud Run |

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GCS_BUCKET_NAME` | Yes | GCS bucket for proof-of-payment files |
| `GOOGLE_SHEETS_ID` | Yes | Google Sheet ID for submission log |
| `APPROVAL_SECRET` | Yes | HMAC secret for legacy email approval tokens |
| `NTFY_ADMIN_TOPIC` | Yes | ntfy.sh topic for admin push notifications (e.g. `admin-alerts-xxxxxxxxxxxx`) |
| `BASE_URL` | Yes | Public URL of the app (used in email links and OAuth redirect) |
| `SECRET_KEY` | Yes | Flask session signing key |
| `GOOGLE_CLIENT_ID` | Yes | OAuth 2.0 client ID (Google Cloud Console) |
| `GOOGLE_CLIENT_SECRET` | Yes | OAuth 2.0 client secret |
| `ADMINISTRATORS` | Yes | Comma-separated admin emails e.g. `you@example.com` |
| `SMTP_HOST` | Yes | SMTP server hostname |
| `SMTP_PORT` | Yes | SMTP port (587 for STARTTLS) |
| `SMTP_USERNAME` | Yes | SMTP login username |
| `SMTP_PASSWORD` | Yes | SMTP login password |
| `FROM_EMAIL` | Yes | Sender address for outbound emails |
| `EKN110_FOLDER_ID` | Yes | Google Drive folder ID for EKN110 notes |
| `EKN120_FOLDER_ID` | Yes | Google Drive folder ID for EKN120 notes |
| `EKN214_FOLDER_ID` | Yes | Google Drive folder ID for EKN214 notes |
| `SENTRY_DSN` | No | Sentry error tracking DSN |

See `.env.example` for a template.

## OAuth setup

1. Create an OAuth 2.0 client in [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials
2. Add these as **Authorised redirect URIs**:
   - `https://<your-production-url>/admin/callback`
   - `http://localhost:5000/admin/callback`
3. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `ADMINISTRATORS` in your environment

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env   # fill in values
export $(grep -v '^#' .env | xargs)

python main.py
```

## Running tests

```bash
pytest tests/
```

## Deployment

Built for **Google Cloud Run**. The `Dockerfile` runs gunicorn with a 120-second timeout to accommodate Cloud Storage, Sheets, Drive, and email operations.

```bash
gcloud run deploy msn-web-app --source .
```

Set all environment variables listed above as Cloud Run secrets or environment variables before deploying.
