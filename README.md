# Miya Study Notes — Submission Portal

Web application for students to submit study note orders for [Miya Study Notes](https://miyastudynotes.co.za).

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
| Deployment | Google Cloud Run (Dockerfile included) |

## Running locally



## Deployment

Built for **Google Cloud Run**. The  runs gunicorn with a 120-second timeout to accommodate the Drive, Sheets, and email operations that happen on approve/deny.


