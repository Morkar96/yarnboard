"""Regression test for GET /api/patterns/community: browsing the community
library is public (unregistered visitors can see what's been uploaded),
while the endpoints that write on a user's behalf -- saving, editing,
submitting, and syncing checklist progress -- stay login-gated."""

from app.extensions import db
from app.models import User


def _register_and_login(client, username):
    email = f"{username}@test.com"
    client.post(
        "/api/register",
        json={"username": username, "email": email, "password": "password123"},
    )
    # Registration leaves the account unverified (see auth/routes.py); this
    # test logs in immediately after, so fast-forward verification directly
    # in the DB rather than parsing the token out of a logged/sent email.
    with client.application.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_verified = True
        db.session.commit()
    client.post("/api/login", json={"email": email, "password": "password123"})


def test_community_patterns_visible_without_login(client):
    resp = client.get("/api/patterns/community")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_community_patterns_visible_once_logged_in(client):
    _register_and_login(client, "owner")
    client.post(
        "/api/patterns/submit",
        json={
            "original_url": "https://example.com/pattern",
            "title": "Test Pattern",
            "instructions": {"Part 1": ["Cast on 10."]},
        },
    )

    resp = client.get("/api/patterns/community")
    assert resp.status_code == 200
    titles = [p["title"] for p in resp.get_json()]
    assert "Test Pattern" in titles


def test_community_patterns_visible_to_anonymous_viewer_too(client):
    _register_and_login(client, "owner")
    client.post(
        "/api/patterns/submit",
        json={
            "original_url": "https://example.com/pattern",
            "title": "Test Pattern",
            "instructions": {"Part 1": ["Cast on 10."]},
        },
    )
    client.post("/api/logout")

    resp = client.get("/api/patterns/community")
    assert resp.status_code == 200
    titles = [p["title"] for p in resp.get_json()]
    assert "Test Pattern" in titles
    # No logged-in user to look progress up for -- every step comes back
    # unchecked rather than erroring or omitting the field.
    assert resp.get_json()[0]["instructions"]["Part 1"][0]["completed"] is False


def test_saving_a_pattern_still_requires_login(client):
    _register_and_login(client, "owner")
    pattern = client.post(
        "/api/patterns/submit",
        json={
            "original_url": "https://example.com/pattern",
            "title": "Test Pattern",
            "instructions": {"Part 1": ["Cast on 10."]},
        },
    ).get_json()["pattern"]
    client.post("/api/logout")

    resp = client.post("/api/patterns/saved", json={"pattern_id": pattern["id"]})
    assert resp.status_code == 401


def test_submitting_a_pattern_still_requires_login(client):
    resp = client.post(
        "/api/patterns/submit",
        json={"original_url": "https://example.com/pattern", "title": "Test Pattern"},
    )
    assert resp.status_code == 401


def test_syncing_progress_still_requires_login(client):
    _register_and_login(client, "owner")
    pattern = client.post(
        "/api/patterns/submit",
        json={
            "original_url": "https://example.com/pattern",
            "title": "Test Pattern",
            "instructions": {"Part 1": ["Cast on 10."]},
        },
    ).get_json()["pattern"]
    client.post("/api/logout")

    resp = client.patch(
        f"/api/patterns/{pattern['id']}/progress",
        json={"part": "Part 1", "index": 0, "completed": True},
    )
    assert resp.status_code == 401
