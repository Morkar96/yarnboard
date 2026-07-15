"""Small helpers shared across blueprints."""

from flask import session


def get_current_user_id():
    """Return the logged-in user's id from the session cookie, or None."""
    return session.get("user_id")
