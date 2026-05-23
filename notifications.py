import logging
import os

import requests

logger = logging.getLogger(__name__)

_NTFY_BASE = "https://ntfy.sh"


def notify_admin_new_submission(submission_data: dict) -> bool:
    """Push a notification to the admin via ntfy.sh when a new submission arrives."""
    topic = os.environ.get("NTFY_ADMIN_TOPIC")
    if not topic:
        logger.warning("NTFY_ADMIN_TOPIC not set — skipping admin push notification")
        return False

    base_url = (os.environ.get("BASE_URL") or "http://localhost:5000").rstrip("/")
    name = f"{submission_data['first_name']} {submission_data['last_name']}"
    module = submission_data["module"]
    chapters = submission_data["chapters"]
    total = submission_data["total_cost"]
    phone = submission_data.get("phone", "")

    title = f"New order: {name}"
    body = f"{module} — {len(chapters)} chapter(s) — R{total}"
    if phone:
        body += f"\n{phone}"

    dashboard_url = f"{base_url}/admin/submissions?status=pending"

    try:
        resp = requests.post(
            f"{_NTFY_BASE}/{topic}",
            data=body.encode("utf-8"),
            headers={
                "Content-Type": "text/plain",
                "Title": title,
                "Priority": "default",
                "Tags": "bell,money_bag",
                "Click": dashboard_url,
            },
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Admin push notification sent for %s", submission_data.get("submission_id"))
        return True
    except Exception as e:
        logger.error("ntfy notification failed for %s: %s", submission_data.get("submission_id"), e)
        return False
