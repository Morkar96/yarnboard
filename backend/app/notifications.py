"""
Per-user notification-settings helpers, shared by every place that creates
an in-app Notification row or sends a notification-related email.

Deliberately thin: each event (pattern updated, pattern shared) still owns
its own email template and its own call site (patterns/routes.py) -- this
module only answers "is this channel on for this user/type" and creates
the in-app Notification row, rather than trying to be a generic dispatch
framework for two event types.
"""

from .extensions import db
from .models import Notification, User

# The fixed set of notification types this app knows about. A settings
# PATCH naming anything outside this set is rejected (see
# patterns/routes.py-adjacent auth routes for the settings endpoint) --
# growing this set is how a new notification type gets added.
NOTIFICATION_TYPES = {"pattern_updated", "pattern_shared"}

DEFAULTS = {"email": True, "in_app": True}


def is_enabled(user: User, notification_type: str, channel: str) -> bool:
    """True unless `user` has explicitly turned `channel` off for
    `notification_type`. A user with no settings row yet, or a type/channel
    added after they registered, defaults to on -- see
    User.notification_settings' docstring for why nothing else in the
    codebase needs to special-case a missing value."""
    settings = (user.notification_settings or {}).get(notification_type, {})
    return settings.get(channel, DEFAULTS[channel])


def create_in_app_notification(user: User, notification_type: str, message: str, link: str | None = None) -> None:
    """Add (and commit) a Notification row for `user`, but only if they
    haven't turned the in_app channel off for this type. No-ops silently
    otherwise -- the caller doesn't need to check is_enabled() itself."""
    if not is_enabled(user, notification_type, "in_app"):
        return
    db.session.add(Notification(user_id=user.id, type=notification_type, message=message, link=link))
    db.session.commit()
