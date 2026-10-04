"""
Tests for pattern visibility: private-by-default patterns, publishing to
the community, per-user sharing (PatternShare), and the
per-uploader/published-only duplicate-URL rule (Pattern.find_duplicate).
See Pattern.is_public's and _can_view's docstrings for the design.
"""

from app.extensions import db
from app.models import Pattern, User


def _register(client, username):
    email = f"{username}@test.com"
    resp = client.post(
        "/api/register",
        json={"username": username, "email": email, "password": "password123"},
    )
    assert resp.status_code == 201
    with client.application.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_verified = True
        db.session.commit()
    return email


def _login(client, email):
    resp = client.post("/api/login", json={"email": email, "password": "password123"})
    assert resp.status_code == 200


def _make_admin(app, email):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.is_admin = True
        db.session.commit()


def _submit_pattern(client, url="https://example.com/pattern", title="Test Pattern"):
    resp = client.post(
        "/api/patterns/submit",
        json={
            "original_url": url,
            "title": title,
            "instructions": {"Part 1": ["Cast on 10."]},
        },
    )
    assert resp.status_code == 201
    return resp.get_json()["pattern"]


def test_new_pattern_is_private_by_default(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    assert pattern["is_public"] is False
    assert client.get("/api/patterns/community").get_json() == []


def test_private_pattern_is_invisible_to_another_user_and_guests(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    resp = client.get(f"/api/patterns/{pattern['id']}")
    assert resp.status_code == 404

    _login(client, _register(client, "other"))
    resp = client.get(f"/api/patterns/{pattern['id']}")
    assert resp.status_code == 404


def test_uploader_and_admin_can_view_their_own_private_pattern(client, app):
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)
    assert client.get(f"/api/patterns/{pattern['id']}").status_code == 200
    client.post("/api/logout")

    admin_email = _register(client, "admin")
    _make_admin(app, admin_email)
    _login(client, admin_email)
    assert client.get(f"/api/patterns/{pattern['id']}").status_code == 200


def test_publish_makes_pattern_visible_everywhere(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    resp = client.post(f"/api/patterns/{pattern['id']}/publish")
    assert resp.status_code == 200
    assert resp.get_json()["pattern"]["is_public"] is True
    client.post("/api/logout")

    assert client.get(f"/api/patterns/{pattern['id']}").status_code == 200
    titles = [p["title"] for p in client.get("/api/patterns/community").get_json()]
    assert "Test Pattern" in titles


def test_publish_is_a_noop_the_second_time(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    client.post(f"/api/patterns/{pattern['id']}/publish")

    resp = client.post(f"/api/patterns/{pattern['id']}/publish")
    assert resp.status_code == 200
    assert resp.get_json()["message"] == "Already public."


def test_non_owner_non_admin_cannot_publish(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    _login(client, _register(client, "other"))
    resp = client.post(f"/api/patterns/{pattern['id']}/publish")
    assert resp.status_code == 403
    assert client.get("/api/patterns/community").get_json() == []


def test_two_users_can_each_privately_submit_the_same_url(client):
    _login(client, _register(client, "first"))
    first = _submit_pattern(client, url="https://example.com/shared-source")
    client.post("/api/logout")

    _login(client, _register(client, "second"))
    second = _submit_pattern(client, url="https://example.com/shared-source")

    assert first["id"] != second["id"]
    with client.application.app_context():
        assert Pattern.query.filter_by(original_url="https://example.com/shared-source").count() == 2


def test_resubmitting_your_own_url_while_still_private_is_rejected(client):
    _login(client, _register(client, "owner"))
    _submit_pattern(client, url="https://example.com/pattern")

    resp = client.post(
        "/api/patterns/submit",
        json={
            "original_url": "https://example.com/pattern",
            "title": "Second attempt",
            "instructions": {},
        },
    )
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "pattern_already_exists"


def test_publishing_when_someone_elses_copy_is_already_public_is_rejected(client):
    # Both submit their own private copy first (submitting is only ever
    # rejected against an *already-public* row -- see find_duplicate), and
    # only then does "first" publish -- otherwise "second" could never
    # have gotten their own private copy to begin with (that scenario is
    # test_submitting_a_url_already_published_by_someone_else_is_rejected
    # below).
    _login(client, _register(client, "first"))
    first = _submit_pattern(client, url="https://example.com/shared-source")
    client.post("/api/logout")

    _login(client, _register(client, "second"))
    second = _submit_pattern(client, url="https://example.com/shared-source")
    client.post("/api/logout")

    _login(client, "first@test.com")
    client.post(f"/api/patterns/{first['id']}/publish")
    client.post("/api/logout")

    _login(client, "second@test.com")
    resp = client.post(f"/api/patterns/{second['id']}/publish")

    assert resp.status_code == 409
    assert resp.get_json()["existing_pattern_id"] == first["id"]


def test_submitting_a_url_already_published_by_someone_else_is_rejected(client):
    _login(client, _register(client, "first"))
    first = _submit_pattern(client, url="https://example.com/shared-source")
    client.post(f"/api/patterns/{first['id']}/publish")
    client.post("/api/logout")

    _login(client, _register(client, "second"))
    resp = client.post(
        "/api/patterns/submit",
        json={
            "original_url": "https://example.com/shared-source",
            "title": "Trying again",
            "instructions": {},
        },
    )
    assert resp.status_code == 409


def test_sharing_grants_view_access_to_one_specific_user(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    friend_email = _register(client, "friend")

    resp = client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "friend"})
    assert resp.status_code == 201
    assert [s["username"] for s in resp.get_json()] == ["friend"]
    client.post("/api/logout")

    _login(client, friend_email)
    assert client.get(f"/api/patterns/{pattern['id']}").status_code == 200
    shared = client.get("/api/patterns/shared-with-me").get_json()
    assert [p["id"] for p in shared] == [pattern["id"]]
    # Sharing is public to nobody else -- the community list stays empty.
    assert client.get("/api/patterns/community").get_json() == []


def test_sharing_is_idempotent(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    _register(client, "friend")

    client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "friend"})
    resp = client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "friend"})
    assert resp.status_code == 201
    assert len(resp.get_json()) == 1


def test_sharing_with_unknown_username_404s(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    resp = client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "nobody"})
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "share_user_not_found"


def test_sharing_with_the_uploader_themselves_is_rejected(client):
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)

    resp = client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "owner"})
    assert resp.status_code == 400


def test_non_owner_non_admin_cannot_share_or_list_shares(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    _login(client, _register(client, "other"))
    assert client.post(
        f"/api/patterns/{pattern['id']}/shares", json={"username": "other"}
    ).status_code == 403
    assert client.get(f"/api/patterns/{pattern['id']}/shares").status_code == 403


def test_unsharing_revokes_access(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    friend_email = _register(client, "friend")
    with client.application.app_context():
        friend_id = User.query.filter_by(email=friend_email).first().id

    client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "friend"})
    resp = client.delete(f"/api/patterns/{pattern['id']}/shares/{friend_id}")
    assert resp.status_code == 200
    client.post("/api/logout")

    _login(client, friend_email)
    assert client.get(f"/api/patterns/{pattern['id']}").status_code == 404
    assert client.get("/api/patterns/shared-with-me").get_json() == []


def test_unsharing_someone_who_was_never_shared_is_a_noop(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    other_email = _register(client, "other")
    with client.application.app_context():
        other_id = User.query.filter_by(email=other_email).first().id

    resp = client.delete(f"/api/patterns/{pattern['id']}/shares/{other_id}")
    assert resp.status_code == 200


def test_toggling_progress_on_a_private_unshared_pattern_404s(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    _login(client, _register(client, "other"))
    resp = client.patch(
        f"/api/patterns/{pattern['id']}/progress",
        json={"part": "Part 1", "index": 0, "completed": True},
    )
    assert resp.status_code == 404


def test_saving_a_private_unshared_pattern_404s(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    _login(client, _register(client, "other"))
    resp = client.post("/api/patterns/saved", json={"pattern_id": pattern["id"]})
    assert resp.status_code == 404


def test_admin_can_view_and_publish_any_private_pattern(client, app):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    admin_email = _register(client, "admin")
    _make_admin(app, admin_email)
    _login(client, admin_email)

    assert client.get(f"/api/patterns/{pattern['id']}").status_code == 200
    resp = client.post(f"/api/patterns/{pattern['id']}/publish")
    assert resp.status_code == 200
    assert resp.get_json()["pattern"]["is_public"] is True
