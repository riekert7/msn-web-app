import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import sentry_sdk

from drive import share_study_materials
from email_utils import (
    send_student_approved_email,
    send_student_confirmation_email,
    send_student_denied_email,
)
from notifications import notify_admin_new_submission
from sheets import update_google_sheets_status
from storage import update_submission_status

logger = logging.getLogger(__name__)


def _run_concurrent(jobs: dict, sid: str) -> None:
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {pool.submit(fn): name for name, fn in jobs.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                ok = future.result()
                logger.info("%s: %s", name, "OK" if ok else "FAILED")
            except Exception as e:
                sentry_sdk.capture_exception(e)
                logger.error("%s error for %s: %s", name, sid, e)


def run_new_submission_tasks(submission_data: dict) -> None:
    sid = submission_data.get("submission_id", "?")
    logger.info("New submission tasks started for %s", sid)
    _run_concurrent({
        "admin_push": lambda: notify_admin_new_submission(submission_data),
        "student_email": lambda: send_student_confirmation_email(submission_data),
    }, sid)


def run_approve_tasks(submission_id: str, data: dict) -> None:
    logger.info("Approve tasks started for %s", submission_id)
    try:
        shared = share_study_materials(data["email"], data["module"], data["chapters"])
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.error("Drive share failed for %s: %s", submission_id, e)
        return
    _run_concurrent({
        "gcs_update": lambda: bool(update_submission_status(submission_id, "approved", {"shared_files": shared})),
        "sheets_update": lambda: update_google_sheets_status(submission_id, "approved"),
        "student_email": lambda: send_student_approved_email(data, shared),
    }, submission_id)


def run_deny_tasks(submission_id: str, data: dict) -> None:
    logger.info("Deny tasks started for %s", submission_id)
    _run_concurrent({
        "sheets_update": lambda: update_google_sheets_status(submission_id, "denied"),
        "student_email": lambda: send_student_denied_email(data),
    }, submission_id)
