"""
Tests for the email-verification gate on registration/login
(backend/app/auth/routes.py): register() no longer implies a usable
session, login() 403s until the account is verified, and verify-email/
resend-verification behave correctly (including the enumeration-safe
resend response and token expiry).
"""

from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import User

CREDENTIALS = {"username": "newuser", "email": "newuser@test.com", "password": "password123"}


def _register(client, **overrides):
    payload = {**CREDENTIALS, **overrides}
    return client.post("/api/register", json=payload)


def test_register_creates_unverified_account_and_does_not_log_in(client, app):
    resp = _register(client)
    assert resp.status_code == 201

    with app.app_context():
        user = User.query.filter_by(email=CREDENTIALS["email"]).first()
        assert user is not None
        assert user.email_verified is False
        assert user.email_verify_token is not None

    profile_resp = client.get("/api/profile")
    assert profile_resp.status_code == 401


def test_login_rejected_before_verification(client):
    _register(client)
    resp = client.post(
        "/api/login", json={"email": CREDENTIALS["email"], "password": CREDENTIALS["password"]}
    )
    assert resp.status_code == 403
    assert "verify" in resp.get_json()["error"].lower()


def test_login_wrong_password_still_401_even_when_unverified(client):
    _register(client)
    resp = client.post(
        "/api/login", json={"email": CREDENTIALS["email"], "password": "wrong-password"}
    )
    assert resp.status_code == 401


def test_verify_email_then_login_succeeds(client, app):
    _register(client)
    with app.app_context():
        token = User.query.filter_by(email=CREDENTIALS["email"]).first().email_verify_token

    verify_resp = client.post("/api/verify-email", json={"token": token})
    assert verify_resp.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email=CREDENTIALS["email"]).first()
        assert user.email_verified is True
        assert user.email_verify_token is None

    login_resp = client.post(
        "/api/login", json={"email": CREDENTIALS["email"], "password": CREDENTIALS["password"]}
    )
    assert login_resp.status_code == 200


def test_verify_email_rejects_unknown_token(client):
    resp = client.post("/api/verify-email", json={"token": "not-a-real-token"})
    assert resp.status_code == 400


def test_verify_email_rejects_expired_token(client, app):
    _register(client)
    with app.app_context():
        user = User.query.filter_by(email=CREDENTIALS["email"]).first()
        token = user.email_verify_token
        user.email_verify_token_created_at = datetime.now(timezone.utc) - timedelta(hours=25)
        db.session.commit()

    resp = client.post("/api/verify-email", json={"token": token})
    assert resp.status_code == 400
    assert "expired" in resp.get_json()["error"].lower()


def test_verify_email_token_is_single_use(client, app):
    _register(client)
    with app.app_context():
        token = User.query.filter_by(email=CREDENTIALS["email"]).first().email_verify_token

    first = client.post("/api/verify-email", json={"token": token})
    assert first.status_code == 200

    second = client.post("/api/verify-email", json={"token": token})
    assert second.status_code == 400


def test_resend_verification_issues_new_token_for_unverified_account(client, app):
    _register(client)
    with app.app_context():
        original_token = User.query.filter_by(email=CREDENTIALS["email"]).first().email_verify_token

    resp = client.post("/api/resend-verification", json={"email": CREDENTIALS["email"]})
    assert resp.status_code == 200

    with app.app_context():
        new_token = User.query.filter_by(email=CREDENTIALS["email"]).first().email_verify_token
        assert new_token != original_token

    # The old token no longer verifies -- only the freshly issued one does.
    assert client.post("/api/verify-email", json={"token": original_token}).status_code == 400
    assert client.post("/api/verify-email", json={"token": new_token}).status_code == 200


def test_resend_verification_same_response_for_unknown_email(client):
    """Enumeration-safety: an email that was never registered gets the
    exact same 200 as a real unverified account, not a 404."""
    resp = client.post("/api/resend-verification", json={"email": "nobody@test.com"})
    assert resp.status_code == 200


def test_resend_verification_noop_for_already_verified_account(client, app):
    _register(client)
    with app.app_context():
        token = User.query.filter_by(email=CREDENTIALS["email"]).first().email_verify_token
    client.post("/api/verify-email", json={"token": token})

    resp = client.post("/api/resend-verification", json={"email": CREDENTIALS["email"]})
    assert resp.status_code == 200

    # Login still works -- resend didn't clear email_verified or mint a
    # dangling token that could confuse a later verify attempt.
    login_resp = client.post(
        "/api/login", json={"email": CREDENTIALS["email"], "password": CREDENTIALS["password"]}
    )
    assert login_resp.status_code == 200
