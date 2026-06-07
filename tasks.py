import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import sentry_sdk

from email_utils import send_student_confirmation_email
from notifications import notify_admin_new_submission

logger = logging.getLogger(__name__)


def run_new_submission_tasks(submission_data: dict) -> None:
    sid = submission_data.get("submission_id", "?")
    logger.info("New submission tasks started for %s", sid)

    jobs = {
        "admin_push": lambda: notify_admin_new_submission(submission_data),
        "student_email": lambda: send_student_confirmation_email(submission_data),
    }

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
