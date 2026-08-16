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
from ..models import User
from ..utils import get_current_user_id

auth_bp = Blueprint("auth", __name__, url_prefix="/api")

# How long a /verify-email link (or a resend of one) stays valid for.
VERIFY_TOKEN_LIFETIME = timedelta(hours=24)


def _issue_verify_token(user: User) -> None:
    """Mints a fresh single-use verification token on `user`, replacing any
    existing one (does not commit -- caller does that)."""
    user.email_verify_token = secrets.token_urlsafe(32)
    user.email_verify_token_created_at = datetime.now(timezone.utc)


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
