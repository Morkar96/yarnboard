"""
Account endpoints: register, login, logout, the current-user profile, and
email verification (verify-email, resend-verification).

Auth is plain server-side session cookies (Flask's signed session, backed
by SECRET_KEY) plus bcrypt password hashing -- no JWTs, no third-party
auth provider. That's a deliberate size-appropriate choice for this app;
see config.py for the cookie's Secure flag in production (a single Flask
service serves both the API and the built frontend, so this is always
same-origin -- no cross-site cookie workaround needed).

register() creates the account unverified and mails a one-time link
(app/email.py); login() then rejects that account (403) until the link is
followed. This means register() no longer implies a usable session --
callers must send the user to check their email rather than treating
registration as an implicit login (see AuthContext.tsx's register()).
"""

import secrets
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, current_app, request, jsonify, session

from ..email import send_verification_email
from ..extensions import db, bcrypt
from ..models import Notification, Pattern, User, UserPatternProgress
from ..notifications import DEFAULTS, NOTIFICATION_TYPES
from ..utils import get_current_user_id

auth_bp = Blueprint("auth", __name__, url_prefix="/api")

# How long a /verify-email link (or a resend of one) stays valid for.
VERIFY_TOKEN_LIFETIME = timedelta(hours=24)


def _issue_verify_token(user: User) -> None:
    """Mints a fresh single-use verification token on `user`, replacing any
    existing one (does not commit -- caller does that)."""
    user.email_verify_token = secrets.token_urlsafe(32)
    user.email_verify_token_created_at = datetime.now(timezone.utc)


def _merge_guest_progress(user: User, guest_progress: dict) -> None:
    """
    Turn a just-registered user's pre-login (localStorage-only, see
    guestProgress.ts) checklist progress into real UserPatternProgress
    rows, so ticking off steps as a guest isn't lost the moment they
    create an account in the same browser.

    `guest_progress` is {pattern_id (as a string key, JSON has no integer
    keys): {part: [bool, ...]}}, the same completed_steps shape
    UserPatternProgress already uses. Unknown/deleted pattern ids are
    skipped rather than erroring -- this is best-effort enrichment of a
    brand-new account, not something registration should ever fail over.
    New rows are stamped with each pattern's *current* instructions_version,
    same as toggle_progress does for a fresh row -- guest progress has no
    version of its own to compare against.
    """
    if not isinstance(guest_progress, dict):
        return
    for pattern_id_str, completed_steps in guest_progress.items():
        try:
            pattern_id = int(pattern_id_str)
        except (TypeError, ValueError):
            continue
        if not isinstance(completed_steps, dict) or not completed_steps:
            continue
        pattern = Pattern.query.get(pattern_id)
        if not pattern:
            continue
        db.session.add(UserPatternProgress(
            user_id=user.id,
            pattern_id=pattern.id,
            completed_steps=completed_steps,
            pattern_version=pattern.instructions_version,
        ))


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not all([username, email, password]):
        return jsonify({
            "error": "username, email and password are required",
            "code": "missing_fields",
        }), 400

    if User.query.filter((User.email == email) | (User.username == username)).first():
        return jsonify({
            "error": "A user with that email or username already exists",
            "code": "account_already_exists",
        }), 409

    user = User(
        username=username,
        email=email,
        password_hash=bcrypt.generate_password_hash(password).decode("utf-8"),
        email_verified=False,
    )
    _issue_verify_token(user)
    db.session.add(user)
    db.session.flush()  # assigns user.id, needed below, before the commit

    _merge_guest_progress(user, data.get("guest_progress"))
    db.session.commit()

    try:
        send_verification_email(user.email, user.username, user.email_verify_token)
    except requests.RequestException:
        # Don't fail registration over a Resend hiccup -- the account
        # exists and /api/resend-verification can always mint a new link.
        current_app.logger.exception("Failed to send verification email to %s", user.email)

    return jsonify({
        "message": f"User {username} created. Check your email to verify your account before logging in.",
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password", "code": "invalid_credentials"}), 401

    if not user.email_verified:
        return jsonify({
            "error": "Please verify your email before logging in. Check your inbox for the link.",
            "code": "email_not_verified",
        }), 403

    session["user_id"] = user.id
    return jsonify({"message": "Login successful", "username": user.username}), 200


@auth_bp.route("/verify-email", methods=["POST"])
def verify_email():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    if not token:
        return jsonify({
            "error": "Missing verification token",
            "code": "missing_verification_token",
        }), 400

    user = User.query.filter_by(email_verify_token=token).first()
    if not user:
        return jsonify({
            "error": "Invalid or already-used verification link",
            "code": "invalid_verification_token",
        }), 400

    issued_at = user.email_verify_token_created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - issued_at > VERIFY_TOKEN_LIFETIME:
        return jsonify({
            "error": "This verification link has expired. Request a new one.",
            "code": "verification_token_expired",
        }), 400

    user.email_verified = True
    user.email_verify_token = None
    user.email_verify_token_created_at = None
    db.session.commit()

    return jsonify({"message": "Email verified! You can now log in."}), 200


@auth_bp.route("/resend-verification", methods=["POST"])
def resend_verification():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    user = User.query.filter_by(email=email).first()
    # Same response regardless of whether the account exists or is already
    # verified, so this endpoint can't be used to enumerate registered
    # emails.
    if user and not user.email_verified:
        _issue_verify_token(user)
        db.session.commit()
        try:
            send_verification_email(user.email, user.username, user.email_verify_token)
        except requests.RequestException:
            current_app.logger.exception("Failed to resend verification email to %s", user.email)

    return jsonify({
        "message": "If that account exists and isn't verified yet, a new link has been sent.",
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"message": "Logout successful"}), 200


@auth_bp.route("/profile", methods=["GET"])
def profile():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized", "code": "unauthorized"}), 401

    user = User.query.get(user_id)
    if not user:
        # Session points at a user that no longer exists; clear it.
        session.pop("user_id", None)
        return jsonify({"error": "Unauthorized", "code": "unauthorized"}), 401

    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
    }), 200


def _require_login():
    """Return (user, None) or (None, error_response) -- same convention as
    the same-named helper in patterns/routes.py and stitch_fiddle/routes.py,
    except this one hands back the User row itself since every caller
    below needs it immediately anyway."""
    user_id = get_current_user_id()
    if not user_id:
        return None, (jsonify({"error": "Unauthorized", "code": "unauthorized"}), 401)
    user = User.query.get(user_id)
    if not user:
        session.pop("user_id", None)
        return None, (jsonify({"error": "Unauthorized", "code": "unauthorized"}), 401)
    return user, None


def _full_notification_settings(user: User) -> dict:
    """Every NOTIFICATION_TYPES key, each with both channels present,
    filling in DEFAULTS for anything not explicitly stored -- shared by
    the GET and PATCH handlers below so a PATCH response always reflects
    the same fully-defaulted view a GET would, not just the partial keys
    that request happened to touch."""
    stored = user.notification_settings or {}
    return {
        notification_type: {
            "email": stored.get(notification_type, {}).get("email", DEFAULTS["email"]),
            "in_app": stored.get(notification_type, {}).get("in_app", DEFAULTS["in_app"]),
        }
        for notification_type in NOTIFICATION_TYPES
    }


@auth_bp.route("/notification-settings", methods=["GET"])
def get_notification_settings():
    """This user's per-type email/in_app toggles, with every known
    NOTIFICATION_TYPES key always present (defaulting to on) even if
    they've never saved a preference -- see User.notification_settings'
    docstring for why the stored column can be sparse."""
    user, error = _require_login()
    if error:
        return error

    return jsonify(_full_notification_settings(user)), 200


@auth_bp.route("/notification-settings", methods=["PATCH"])
def update_notification_settings():
    """
    Partial update: body is {notification_type: {"email": bool, "in_app":
    bool}, ...} for whichever type(s) are changing -- types/channels not
    included are left as they were. Rejects any type outside
    NOTIFICATION_TYPES so a typo doesn't silently create a dead setting
    nothing ever reads.
    """
    user, error = _require_login()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be an object.", "code": "missing_fields"}), 400

    unknown = set(data.keys()) - NOTIFICATION_TYPES
    if unknown:
        return jsonify({
            "error": f"Unknown notification type(s): {', '.join(sorted(unknown))}.",
            "code": "invalid_notification_type",
        }), 400

    settings = dict(user.notification_settings or {})
    for notification_type, channels in data.items():
        if not isinstance(channels, dict):
            continue
        existing = dict(settings.get(notification_type, {}))
        if "email" in channels:
            existing["email"] = bool(channels["email"])
        if "in_app" in channels:
            existing["in_app"] = bool(channels["in_app"])
        settings[notification_type] = existing

    user.notification_settings = settings
    db.session.commit()

    return jsonify(_full_notification_settings(user)), 200


@auth_bp.route("/notifications", methods=["GET"])
def list_notifications():
    """This user's in-app notification inbox, newest first."""
    user, error = _require_login()
    if error:
        return error

    notifications = (
        Notification.query.filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return jsonify([n.to_dict() for n in notifications]), 200


@auth_bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
def mark_notification_read(notification_id):
    """Mark one notification read. 404s if it doesn't belong to this user
    (never leaks whether some other user's notification id exists)."""
    user, error = _require_login()
    if error:
        return error

    notification = Notification.query.filter_by(id=notification_id, user_id=user.id).first()
    if not notification:
        return jsonify({"error": "Notification not found.", "code": "notification_not_found"}), 404

    notification.read = True
    db.session.commit()
    return jsonify(notification.to_dict()), 200


@auth_bp.route("/notifications/read-all", methods=["POST"])
def mark_all_notifications_read():
    """Mark every one of this user's unread notifications read in one
    call, for a "clear all" action in the inbox UI."""
    user, error = _require_login()
    if error:
        return error

    Notification.query.filter_by(user_id=user.id, read=False).update({"read": True})
    db.session.commit()
    return jsonify({"message": "All notifications marked read."}), 200
