# Miya Study Notes — Submission Portal

Web application for students to submit study note orders for Miya Study Notes.

## What it does

Students fill in a form to order printed study notes for specific modules and chapters. The app handles the full submission workflow:

- Accepts proof-of-payment file uploads (PDF, JPG, PNG — max 5 MB) to **Google Cloud Storage**
- Logs each submission to a **Google Sheet** for admin tracking (timestamp, student details, module, chapters, cost, file)
- Emails the admin HMAC-signed approve/deny links so submissions can be actioned without logging in
- Sends the student a confirmation email on submission and a follow-up on approval or denial

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python / Flask |
| File storage | Google Cloud Storage |
| Submission log | Google Sheets API |
| Deployment | Google Cloud Run |

## Running locally

```bash
pip install -r requirements.txt

export GCS_BUCKET_NAME=<your-bucket>
export GOOGLE_SHEETS_ID=<your-sheet-id>
export APPROVAL_SECRET=<random-secret>

python main.py
```

## Deployment

Built for **Google Cloud Run**. The `Dockerfile` runs gunicorn with a 120-second timeout to accommodate the Cloud Storage, Sheets, and email operations that happen on approve/deny.

```bash
gcloud run deploy msn-web-app --source .
```
