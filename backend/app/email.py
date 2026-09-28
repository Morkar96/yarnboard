"""
Outbound email, via Resend's plain HTTP API (https://resend.com/docs/api-reference/emails/send-email).

Uses `requests` directly rather than the `resend` PyPI package -- it's a
single POST with a JSON body and a bearer token, not worth a whole new
dependency for.

Each email category uses its own Resend API key, matching how the
Resend account itself is organized (separate keys per sending purpose,
so each can be revoked/rate-limited/monitored independently):
  - RESEND_ONBOARDING: account-lifecycle emails (send_verification_email).
  - RESEND_NOTIFICATIONS: activity emails about a pattern
    (send_pattern_updated_email, send_pattern_shared_email).
  - RESEND_NEWSLETTER: reserved for a future newsletter feature -- no
    sender uses it yet, since no newsletter content/trigger exists.
If a given category's key isn't set, sends in that category are logged
instead of actually delivered -- the same graceful-fallback spirit as
DATABASE_URL defaulting to local SQLite when unset, so local dev/testing
never needs real Resend keys.
"""

import html
import os

import requests
from flask import current_app

RESEND_API_URL = "https://api.resend.com/emails"
REQUEST_TIMEOUT_SECONDS = 10


def _deliver(api_key_env_var: str, to_email: str, subject: str, html_body: str) -> None:
    """
    Shared send-or-log core for every email category below. Looks up
    `api_key_env_var` (e.g. "RESEND_ONBOARDING") at call time (not
    import time) so tests can monkeypatch it per-test. Raises
    requests.RequestException on delivery failure -- every caller here
    treats that as non-fatal (see each public function's docstring for
    why), so this never raises for a *missing* key, only for a failed
    HTTP call once a key is present.
    """
    api_key = os.environ.get(api_key_env_var)
    from_email = os.environ.get("RESEND_FROM_EMAIL", "Yarnboard <notifications@yarnboard.app>")

    if not api_key:
        # current_app.logger (not a bare module logger) so this is
        # actually visible without extra logging config -- Flask attaches
        # a handler to it by default even outside debug mode, whereas a
        # plain `logging.getLogger(__name__).info(...)` here would
        # silently vanish (no handler, default WARNING level).
        current_app.logger.warning(
            "%s not set -- would send email to %s: %s", api_key_env_var, to_email, subject
        )
        return

    response = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"from": from_email, "to": [to_email], "subject": subject, "html": html_body},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def send_verification_email(to_email: str, username: str, token: str) -> None:
    """
    Mail the one-time verification link for a just-registered account.
    Raises requests.RequestException on delivery failure -- the caller
    (auth/routes.py's register()/resend_verification()) treats that as
    non-fatal, since a Resend outage shouldn't fail registration outright
    when the user can always ask for the link again.
    """
    app_url = os.environ.get("PUBLIC_APP_URL", "http://localhost:5173")
    verify_url = f"{app_url}/verify-email?token={token}"

    subject = "Verify your Yarnboard email"
    html_body = (
        f"<p>Welcome to Yarnboard, <strong>{html.escape(username)}</strong>!</p>"
        f"<p>Please verify your email address to activate your account.</p>"
        f'<p><a href="{verify_url}">Verify your email</a></p>'
        f"<p>This link expires in 24 hours.</p>"
    )

    _deliver("RESEND_ONBOARDING", to_email, subject, html_body)


def send_pattern_updated_email(to_email: str, pattern) -> None:
    """
    Notify `to_email` that `pattern` (a Pattern model instance) has been
    edited. Raises requests.RequestException on delivery failure -- the
    caller (patterns/routes.py's _notify_progress_users) is responsible for
    catching that per-recipient so one failed send doesn't stop the others
    or affect the edit that triggered it.
    """
    app_url = os.environ.get("PUBLIC_APP_URL", "http://localhost:5173")
    pattern_url = f"{app_url}/pattern/{pattern.id}"

    # pattern.title is attacker-controlled (set by whoever uploaded the
    # pattern, not by `to_email`'s recipient) and gets interpolated into
    # HTML sent to a third party -- escape it (for the HTML body only;
    # `subject` is plain text, not markup, so it's left as-is) so it can't
    # inject markup into the notification, e.g. a fake link disguised as
    # the pattern name.
    subject = f'"{pattern.title}" has been updated'
    html_body = (
        f"<p>A pattern you've been tracking on Yarnboard, "
        f"<strong>{html.escape(pattern.title)}</strong>, has just been edited.</p>"
        f"<p>Since the instructions changed, your saved checklist progress "
        f"on it has been reset.</p>"
        f'<p><a href="{pattern_url}">View the updated pattern</a></p>'
    )

    _deliver("RESEND_NOTIFICATIONS", to_email, subject, html_body)


def send_pattern_shared_email(to_email: str, sharer_username: str, pattern) -> None:
    """
    Notify `to_email` that `sharer_username` gave them access to `pattern`.
    Raises requests.RequestException on delivery failure -- the caller
    (patterns/routes.py's share_pattern) treats that the same way every
    other best-effort notification email here does: log and move on,
    since the share itself already succeeded regardless of the email.
    """
    app_url = os.environ.get("PUBLIC_APP_URL", "http://localhost:5173")
    pattern_url = f"{app_url}/pattern/{pattern.id}"

    # Both sharer_username and pattern.title are attacker-controlled (the
    # sharer picks their own username; pattern.title is set by whoever
    # uploaded it, not necessarily sharer_username) -- escape both before
    # interpolating into HTML sent to a third party, same reasoning as
    # send_pattern_updated_email above. `subject` is plain text, left as-is.
    subject = f'{sharer_username} shared "{pattern.title}" with you'
    html_body = (
        f"<p><strong>{html.escape(sharer_username)}</strong> shared a pattern with you on "
        f"Yarnboard: <strong>{html.escape(pattern.title)}</strong>.</p>"
        f'<p><a href="{pattern_url}">View the pattern</a></p>'
    )

    _deliver("RESEND_NOTIFICATIONS", to_email, subject, html_body)
