"""
Regression tests for the findings from the manual security audit of
config.py, auth/routes.py, patterns/routes.py, and email.py. Each test
below is named after the specific vulnerability it guards against;
see PR history / commit messages for the audit writeup these were added
alongside.

The SSRF/local-file-read fix in the scraper itself (app/scraper.py) is
covered at the unit level in test_scraper.py -- test_preview_pattern_
rejects_private_and_file_urls below is the route-level integration check
confirming that guard is actually wired into POST /api/patterns/preview,
not just present in the module.
"""

import app.config as config_module
import pytest

from app import create_app
from app.extensions import db, limiter
from app.models import User


def _register(client, username, password="password123"):
    email = f"{username}@test.com"
    resp = client.post(
        "/api/register",
        json={"username": username, "email": email, "password": password},
    )
    assert resp.status_code == 201
    with client.application.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_verified = True
        db.session.commit()
    return email


# --- SECRET_KEY must not silently default in production ---------------


def test_create_app_refuses_to_start_in_production_with_default_secret_key(monkeypatch):
    monkeypatch.setattr(config_module.BaseConfig, "SECRET_KEY", config_module.INSECURE_DEFAULT_SECRET_KEY)
    monkeypatch.setenv("FLASK_ENV", "production")

    with pytest.raises(RuntimeError):
        create_app()


def test_create_app_starts_in_production_with_a_real_secret_key(monkeypatch):
    monkeypatch.setattr(config_module.BaseConfig, "SECRET_KEY", "a-real-random-secret-value")
    monkeypatch.setenv("FLASK_ENV", "production")

    flask_app = create_app(config_overrides={"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    assert flask_app.config["SECRET_KEY"] == "a-real-random-secret-value"


# --- Password strength -------------------------------------------------


def test_register_rejects_a_too_short_password(client):
    resp = client.post(
        "/api/register",
        json={"username": "shortpw", "email": "shortpw@test.com", "password": "abc123"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "password_too_short"


def test_register_accepts_a_password_at_the_minimum_length(client):
    resp = client.post(
        "/api/register",
        json={"username": "minpw", "email": "minpw@test.com", "password": "eightchr"},
    )
    assert resp.status_code == 201


# --- Login timing side-channel (email enumeration) ---------------------


def test_login_with_nonexistent_email_still_runs_a_password_check(client, monkeypatch):
    """
    Regression test for a timing side-channel: login() used to
    short-circuit `if not user or not bcrypt.check_password_hash(...)`
    before the (deliberately slow) bcrypt call ran when the account
    didn't exist, making response time distinguish a real email from a
    fake one. The fix always calls bcrypt.check_password_hash -- against
    a fixed dummy hash when there's no such user -- so this asserts that
    call actually happens rather than being skipped, which is what a real
    timing measurement would otherwise be needed to prove.
    """
    import app.auth.routes as auth_routes

    calls = []
    original = auth_routes.bcrypt.check_password_hash

    def _tracking_check(pw_hash, password):
        calls.append(pw_hash)
        return original(pw_hash, password)

    monkeypatch.setattr(auth_routes.bcrypt, "check_password_hash", _tracking_check)

    resp = client.post(
        "/api/login",
        json={"email": "no-such-account@test.com", "password": "whatever123"},
    )

    assert resp.status_code == 401
    assert resp.get_json()["code"] == "invalid_credentials"
    assert len(calls) == 1
    assert calls[0] == auth_routes._DUMMY_PASSWORD_HASH


def test_login_with_real_email_wrong_password_also_runs_check_against_real_hash(client, monkeypatch):
    email = _register(client, "realuser")

    import app.auth.routes as auth_routes

    calls = []
    original = auth_routes.bcrypt.check_password_hash

    def _tracking_check(pw_hash, password):
        calls.append(pw_hash)
        return original(pw_hash, password)

    monkeypatch.setattr(auth_routes.bcrypt, "check_password_hash", _tracking_check)

    resp = client.post("/api/login", json={"email": email, "password": "wrong-password"})

    assert resp.status_code == 401
    assert len(calls) == 1
    assert calls[0] != auth_routes._DUMMY_PASSWORD_HASH


# --- Rate limiting -------------------------------------------------
#
# The shared `app` fixture disables rate limiting (see conftest.py) so
# the rest of the suite isn't affected by the limiter's cross-test shared
# storage. These tests build their own app with it explicitly re-enabled,
# and reset the limiter's storage first so counts from whatever ran
# before this test in the same pytest process don't leak in.


@pytest.fixture()
def rate_limited_client():
    # Built independently of the shared `app`/`client` fixtures rather
    # than toggling their RATELIMIT_ENABLED after the fact: Flask-Limiter
    # reads that config once, inside init_app (called from create_app),
    # and caches it on the shared `limiter` object -- flipping
    # app.config afterward has no effect on an already-initialized app.
    import os
    import tempfile

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    flask_app = create_app(config_overrides={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "RATELIMIT_ENABLED": True,
    })
    with flask_app.app_context():
        db.create_all()
        limiter.reset()
        yield flask_app.test_client()
        db.session.remove()
        db.drop_all()
        limiter.reset()

    os.close(db_fd)
    os.unlink(db_path)


def test_login_is_rate_limited_per_ip(rate_limited_client):
    email = _register(rate_limited_client, "ratelimited")

    responses = [
        rate_limited_client.post("/api/login", json={"email": email, "password": "wrong"})
        for _ in range(25)
    ]

    assert any(r.status_code == 429 for r in responses)


def test_register_is_rate_limited_per_ip(rate_limited_client):
    responses = [
        rate_limited_client.post(
            "/api/register",
            json={"username": f"floodreg{i}", "email": f"floodreg{i}@test.com", "password": "password123"},
        )
        for i in range(15)
    ]

    assert any(r.status_code == 429 for r in responses)


def test_resend_verification_is_rate_limited_per_ip(rate_limited_client):
    email = _register(rate_limited_client, "resendflood")

    responses = [
        rate_limited_client.post("/api/resend-verification", json={"email": email})
        for _ in range(10)
    ]

    assert any(r.status_code == 429 for r in responses)


# --- SSRF / local-file-read, at the route level -------------------------


def test_preview_pattern_rejects_private_and_file_urls(client):
    _register(client, "previewer")
    client.post("/api/login", json={"email": "previewer@test.com", "password": "password123"})

    for bad_url in (
        "file:///etc/passwd",
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost:5001/",
    ):
        resp = client.post("/api/patterns/preview", json={"url": bad_url})
        assert resp.status_code == 502, f"{bad_url} was not rejected: {resp.get_json()}"
        assert resp.get_json()["code"] == "scraper_error"


# --- HTML injection in outbound emails ----------------------------------
#
# Both send_verification_email's `username` and send_pattern_updated_
# email's `pattern.title` are attacker-controlled text (a chosen
# username; a pattern title set by whoever uploaded it) that lands in an
# HTML email sent to someone else. Both must be escaped before
# interpolation, or a crafted value could inject markup -- e.g. a fake
# link disguised as the pattern name -- into a real recipient's inbox.


class _FakePattern:
    def __init__(self, id, title):
        self.id = id
        self.title = title


def test_send_verification_email_escapes_username_in_html_body(monkeypatch):
    import app.email as email_module

    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

    def _fake_post(url, headers, json, timeout):
        captured["json"] = json
        return _FakeResponse()

    monkeypatch.setattr(email_module.requests, "post", _fake_post)

    payload_username = "<img src=x onerror=alert(1)>"
    flask_app = create_app(config_overrides={"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with flask_app.app_context():
        email_module.send_verification_email("victim@test.com", payload_username, "sometoken")

    html_body = captured["json"]["html"]
    assert payload_username not in html_body
    assert "&lt;img" in html_body


def test_send_pattern_updated_email_escapes_title_in_html_body(monkeypatch):
    import app.email as email_module

    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

    def _fake_post(url, headers, json, timeout):
        captured["json"] = json
        return _FakeResponse()

    monkeypatch.setattr(email_module.requests, "post", _fake_post)

    payload_title = '<a href="https://evil.example">Click here</a>'
    pattern = _FakePattern(id=1, title=payload_title)
    flask_app = create_app(config_overrides={"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with flask_app.app_context():
        email_module.send_pattern_updated_email("victim@test.com", pattern)

    html_body = captured["json"]["html"]
    assert payload_title not in html_body
    assert "&lt;a href=" in html_body
