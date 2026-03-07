# Webapp – What’s Here and Where We’re Headed

**Goal:** One Flask app that replaces the old Netlify + Cloud Functions setup. Students submit via a form; admin approves or denies via email links; student gets Drive access and emails. Deploy to **Google Cloud Run** (free tier). See project root `.cursor/rules/architecture-build-plan.mdc` for the full system context.

## What’s in This Repo

| Part | Role |
|------|------|
| `main.py` | Flask app: routes, validation, GCS, Sheets, SMTP, Drive sharing, signed approve/deny. |
| `templates/form.html` | Study-notes request form (modules, chapters, proof-of-payment upload). |
| `static/` | `script.js`, `styles.css` for the form. |
| `requirements.txt` | Flask, Gunicorn, google-cloud-storage, google-auth, google-api-python-client. |

**Routes**

- `GET /` – Serves the form.
- `POST /submit` – Accepts form + file; writes to GCS + metadata; logs to Sheets; queues **background** SMTP (admin email with PoP attachment + Approve/Deny links, student confirmation). Returns 200 quickly.
- `GET /approve/<id>?token=...` – Signed link from admin email. Loads submission, shares Drive chapters with student, updates status/Sheets, emails student. Returns HTML.
- `GET /deny/<id>?token=...` – Signed link from admin email. Marks denied, emails student. Returns HTML.
- `GET /healthz` – Health check.

**Config (env)**

- GCS: `GCS_BUCKET_NAME`, `GOOGLE_APPLICATION_CREDENTIALS` (local).
- Sheets: `GOOGLE_SHEETS_ID`.
- SMTP: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `FROM_EMAIL`; `ADMIN_EMAIL` for new-submission notifications.
- Approve/Deny links: `APPROVAL_SECRET`, `BASE_URL`.
- Drive: `EKN110_FOLDER_ID`, `EKN120_FOLDER_ID`, `EKN214_FOLDER_ID`.

## What We’re Building Toward

1. **Local:** Run with `python main.py` (or Gunicorn), load env from project root `.env`. Form works; GCS + Sheets + emails (if SMTP is reachable).
2. **Cloud Run:** Containerize (Dockerfile + Gunicorn on `$PORT`), deploy with `gcloud run deploy`, set the same env vars. Use `BASE_URL` = Cloud Run URL so admin email links point at the service.
3. **No Discord in this app** – approval is email-only (admin clicks Approve/Deny in the message). GCS lifecycle rule cleans old submission files; no delete-on-approve in code.

## Quick Run (Local)

From repo root, with `.env` present:

```bash
cd webapp && source .venv/bin/activate && export $(grep -v '^#' ../.env | xargs) && python main.py
```

Open `http://localhost:5000`, submit the form. Check terminal for `[EMAIL]` logs (emails are sent in a background thread).

## Developing elsewhere (what you need outside `webapp/`)

The app only reads **environment variables**; it does not assume a fixed repo layout. To run the app in another clone or machine you need:

1. **`.env`** (or the same vars in the environment)  
   Put it in the parent of `webapp/` (or anywhere) and load it before running, e.g.  
   `export $(grep -v '^#' ../.env | xargs)`.  
   Do not commit `.env`.

2. **Service account key file**  
   `GOOGLE_APPLICATION_CREDENTIALS` in `.env` must point to a **JSON key file** for GCS, Drive, and Sheets (e.g. `../.keys/miya-study-notes-….json` or `../keys/service-account-key.json`). Create the key in Google Cloud Console, save the file, and set the path in `.env`.  
   Do not commit the key file or `.keys/` / `keys/`.

That’s it: **`.env`** and the **key file** (path set in `.env`). No other files outside `webapp/` are required to run the app.
