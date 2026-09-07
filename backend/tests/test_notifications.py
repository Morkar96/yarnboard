"""
Tests for: per-user notification settings (GET/PATCH
/api/notification-settings), the in-app notification inbox (list/mark
read/mark all read), notifications actually firing on pattern-shared and
pattern-updated events, and merging a guest's pre-login checklist
progress into a brand-new account at registration time. See
notifications.py, auth/routes.py's register()/_merge_guest_progress, and
patterns/routes.py's share_pattern/_notify_progress_users.
"""

from app.extensions import db
from app.models import Pattern, User, UserPatternProgress


def _register(client, username, guest_progress=None):
    email = f"{username}@test.com"
    body = {"username": username, "email": email, "password": "password123"}
    if guest_progress is not None:
        body["guest_progress"] = guest_progress
    resp = client.post("/api/register", json=body)
    assert resp.status_code == 201
    with client.application.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_verified = True
        db.session.commit()
    return email


def _login(client, email):
    resp = client.post("/api/login", json={"email": email, "password": "password123"})
    assert resp.status_code == 200


def _submit_pattern(client, url="https://example.com/pattern", title="Test Pattern"):
    resp = client.post(
        "/api/patterns/submit",
        json={"original_url": url, "title": title, "instructions": {"Part 1": ["Cast on 10.", "Row 1."]}},
    )
    assert resp.status_code == 201
    return resp.get_json()["pattern"]


# --- notification settings ----------------------------------------------

def test_default_settings_are_all_on(client):
    _login(client, _register(client, "owner"))
    resp = client.get("/api/notification-settings")
    assert resp.status_code == 200
    settings = resp.get_json()
    assert settings["pattern_updated"] == {"email": True, "in_app": True}
    assert settings["pattern_shared"] == {"email": True, "in_app": True}


def test_partial_update_only_touches_the_given_type_and_channel(client):
    _login(client, _register(client, "owner"))
    resp = client.patch("/api/notification-settings", json={"pattern_shared": {"email": False}})
    assert resp.status_code == 200
    settings = resp.get_json()
    assert settings["pattern_shared"] == {"email": False, "in_app": True}
    assert settings["pattern_updated"] == {"email": True, "in_app": True}


def test_unknown_notification_type_is_rejected(client):
    _login(client, _register(client, "owner"))
    resp = client.patch("/api/notification-settings", json={"made_up_type": {"email": False}})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_notification_type"


def test_notification_settings_require_login(client):
    assert client.get("/api/notification-settings").status_code == 401
    assert client.patch("/api/notification-settings", json={}).status_code == 401


# --- in-app notification inbox -------------------------------------------

def test_sharing_a_pattern_creates_an_in_app_notification_for_the_recipient(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    _register(client, "friend")
    client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "friend"})
    client.post("/api/logout")

    _login(client, "friend@test.com")
    resp = client.get("/api/notifications")
    assert resp.status_code == 200
    notifications = resp.get_json()
    assert len(notifications) == 1
    assert notifications[0]["type"] == "pattern_shared"
    assert notifications[0]["read"] is False
    assert notifications[0]["link"] == f"/pattern/{pattern['id']}"


def test_disabling_in_app_for_pattern_shared_suppresses_the_notification(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    _register(client, "friend")
    client.post("/api/logout")

    _login(client, "friend@test.com")
    client.patch("/api/notification-settings", json={"pattern_shared": {"in_app": False}})
    client.post("/api/logout")

    _login(client, "owner@test.com")
    client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "friend"})
    client.post("/api/logout")

    _login(client, "friend@test.com")
    assert client.get("/api/notifications").get_json() == []


def test_mark_notification_read(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    _register(client, "friend")
    client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "friend"})
    client.post("/api/logout")

    _login(client, "friend@test.com")
    notification_id = client.get("/api/notifications").get_json()[0]["id"]
    resp = client.post(f"/api/notifications/{notification_id}/read")
    assert resp.status_code == 200
    assert resp.get_json()["read"] is True


def test_cannot_mark_someone_elses_notification_read(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    _register(client, "friend")
    client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "friend"})
    client.post("/api/logout")

    _login(client, "friend@test.com")
    notification_id = client.get("/api/notifications").get_json()[0]["id"]
    client.post("/api/logout")

    _login(client, _register(client, "stranger"))
    resp = client.post(f"/api/notifications/{notification_id}/read")
    assert resp.status_code == 404


def test_mark_all_read(client):
    _login(client, _register(client, "owner"))
    p1 = _submit_pattern(client, url="https://example.com/a", title="A")
    p2 = _submit_pattern(client, url="https://example.com/b", title="B")
    _register(client, "friend")
    client.post(f"/api/patterns/{p1['id']}/shares", json={"username": "friend"})
    client.post(f"/api/patterns/{p2['id']}/shares", json={"username": "friend"})
    client.post("/api/logout")

    _login(client, "friend@test.com")
    assert len(client.get("/api/notifications").get_json()) == 2
    client.post("/api/notifications/read-all")
    notifications = client.get("/api/notifications").get_json()
    assert all(n["read"] for n in notifications)


def test_editing_instructions_notifies_users_with_progress(client, app):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    _register(client, "friend")
    client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "friend"})
    client.post("/api/logout")

    _login(client, "friend@test.com")
    client.patch(
        f"/api/patterns/{pattern['id']}/progress",
        json={"part": "Part 1", "index": 0, "completed": True},
    )
    client.post("/api/logout")

    _login(client, "owner@test.com")
    client.patch(
        f"/api/patterns/{pattern['id']}",
        json={"title": pattern["title"], "instructions": {"Part 1": ["Cast on 10.", "Row 1 changed."]}},
    )
    client.post("/api/logout")

    _login(client, "friend@test.com")
    notifications = client.get("/api/notifications").get_json()
    assert any(n["type"] == "pattern_updated" for n in notifications)


# --- guest progress merge on registration --------------------------------

def test_guest_progress_is_merged_into_the_new_account(client, app):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    pattern_id = pattern["id"]
    client.post(f"/api/patterns/{pattern_id}/publish")
    client.post("/api/logout")

    guest_progress = {str(pattern_id): {"Part 1": [True, False]}}
    _register(client, "newcomer", guest_progress=guest_progress)

    with app.app_context():
        user = User.query.filter_by(email="newcomer@test.com").first()
        progress = UserPatternProgress.query.filter_by(user_id=user.id, pattern_id=pattern_id).first()
        assert progress is not None
        assert progress.completed_steps == {"Part 1": [True, False]}
        assert progress.pattern_version == Pattern.query.get(pattern_id).instructions_version


def test_guest_progress_for_a_nonexistent_pattern_is_skipped_silently(client):
    resp = client.post(
        "/api/register",
        json={
            "username": "newcomer",
            "email": "newcomer@test.com",
            "password": "password123",
            "guest_progress": {"999999": {"Part 1": [True]}},
        },
    )
    assert resp.status_code == 201
