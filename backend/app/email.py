"""
Outbound email, via Resend's plain HTTP API (https://resend.com/docs/api-reference/emails/send-email).

Uses `requests` directly rather than the `resend` PyPI package -- it's a
single POST with a JSON body and a bearer token, not worth a whole new
dependency for.

If RESEND_API_KEY isn't set, sends are logged instead of actually
delivered -- the same graceful-fallback spirit as DATABASE_URL defaulting
to local SQLite when unset, so local dev/testing never needs a real
Resend account.
"""

import os

import requests
from flask import current_app

RESEND_API_URL = "https://api.resend.com/emails"
REQUEST_TIMEOUT_SECONDS = 10


def send_pattern_updated_email(to_email: str, pattern) -> None:
    """
    Notify `to_email` that `pattern` (a Pattern model instance) has been
    edited. Raises requests.RequestException on delivery failure -- the
    caller (patterns/routes.py's _notify_progress_users) is responsible for
    catching that per-recipient so one failed send doesn't stop the others
    or affect the edit that triggered it.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    from_email = os.environ.get("RESEND_FROM_EMAIL", "Yarnboard <notifications@yarnboard.app>")
    app_url = os.environ.get("PUBLIC_APP_URL", "http://localhost:5173")
    pattern_url = f"{app_url}/pattern/{pattern.id}"

    subject = f'"{pattern.title}" has been updated'
    html = (
        f"<p>A pattern you've been tracking on Yarnboard, "
        f"<strong>{pattern.title}</strong>, has just been edited.</p>"
        f"<p>Since the instructions changed, your saved checklist progress "
        f"on it has been reset.</p>"
        f'<p><a href="{pattern_url}">View the updated pattern</a></p>'
    )

    if not api_key:
        # current_app.logger (not a bare module logger) so this is
        # actually visible without extra logging config -- Flask attaches
        # a handler to it by default even outside debug mode, whereas a
        # plain `logging.getLogger(__name__).info(...)` here would
        # silently vanish (no handler, default WARNING level).
        current_app.logger.warning(
            "RESEND_API_KEY not set -- would send email to %s: %s", to_email, subject
        )
        return

    response = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"from": from_email, "to": [to_email], "subject": subject, "html": html},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
