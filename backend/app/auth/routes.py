"""
Account endpoints: register, login, logout, and the current-user profile.

Auth is plain server-side session cookies (Flask's signed session, backed
by SECRET_KEY) plus bcrypt password hashing -- no JWTs, no third-party
auth provider. That's a deliberate size-appropriate choice for this app;
see config.py for how the session cookie is hardened for cross-origin use
in production (frontend and backend are separate Render services).
"""

from flask import Blueprint, request, jsonify, session

from ..extensions import db, bcrypt
from ..models import User
from ..utils import get_current_user_id

auth_bp = Blueprint("auth", __name__, url_prefix="/api")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not all([username, email, password]):
        return jsonify({"error": "username, email and password are required"}), 400

    if User.query.filter((User.email == email) | (User.username == username)).first():
        return jsonify({"error": "A user with that email or username already exists"}), 409

    user = User(
        username=username,
        email=email,
        password_hash=bcrypt.generate_password_hash(password).decode("utf-8"),
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({"message": f"User {username} created successfully"}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if user and bcrypt.check_password_hash(user.password_hash, password):
        session["user_id"] = user.id
        return jsonify({"message": "Login successful", "username": user.username}), 200

    return jsonify({"error": "Invalid email or password"}), 401


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"message": "Logout successful"}), 200


@auth_bp.route("/profile", methods=["GET"])
def profile():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    user = User.query.get(user_id)
    if not user:
        # Session points at a user that no longer exists; clear it.
        session.pop("user_id", None)
        return jsonify({"error": "Unauthorized"}), 401

    return jsonify({"id": user.id, "username": user.username, "email": user.email}), 200
