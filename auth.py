import hashlib
import hmac
import os


def approval_token(submission_id: str) -> str:
    """HMAC-SHA256 token for approve/deny links — prevents forgery."""
    secret = os.environ.get("APPROVAL_SECRET", "").encode()
    return hmac.new(secret, submission_id.encode(), hashlib.sha256).hexdigest()


def verify_approval_token(submission_id: str, token: str) -> bool:
    return bool(token) and hmac.compare_digest(approval_token(submission_id), token)
