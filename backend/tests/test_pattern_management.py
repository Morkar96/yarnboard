"""
Tests for the newer pattern-management endpoints: unpublish (and the
dedup-URL-freeing it implies), delete, edit-level pattern sharing
(PatternShare.can_edit + PATCH .../shares/<user_id>), and the
already_shared_with_you preview warning. See patterns/routes.py's
unpublish_pattern/delete_pattern/share_pattern/update_pattern_share and
_shared_pattern_id for the behavior under test.
"""

from app.extensions import db
from app.models import Pattern, PatternShare, User, UserPatternProgress


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


def _submit_pattern(client, url="https://example.com/pattern", title="Test Pattern"):
    resp = client.post(
        "/api/patterns/submit",
        json={"original_url": url, "title": title, "instructions": {"Part 1": ["Cast on 10."]}},
    )
    assert resp.status_code == 201
    return resp.get_json()["pattern"]


# --- unpublish -------------------------------------------------------

def test_unpublish_makes_a_public_pattern_private_again(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    client.post(f"/api/patterns/{pattern['id']}/publish")

    resp = client.post(f"/api/patterns/{pattern['id']}/unpublish")
    assert resp.status_code == 200
    assert resp.get_json()["pattern"]["is_public"] is False


def test_unpublish_is_a_noop_when_already_private(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    resp = client.post(f"/api/patterns/{pattern['id']}/unpublish")
    assert resp.status_code == 200
    assert "Already private" in resp.get_json()["message"]


def test_non_manager_cannot_unpublish(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    client.post(f"/api/patterns/{pattern['id']}/publish")
    client.post("/api/logout")

    _login(client, _register(client, "stranger"))
    resp = client.post(f"/api/patterns/{pattern['id']}/unpublish")
    assert resp.status_code == 403


def test_unpublishing_frees_the_url_for_another_uploaders_publish(client):
    url = "https://example.com/shared-source"

    # Both submit their own private copy first -- find_duplicate blocks
    # submitting a *private* copy of a URL some pattern already has
    # published, so this has to happen before first publishes.
    _login(client, _register(client, "first"))
    first_pattern = _submit_pattern(client, url=url, title="First's copy")
    client.post("/api/logout")

    _login(client, _register(client, "second"))
    second_pattern = _submit_pattern(client, url=url, title="Second's copy")
    client.post("/api/logout")

    _login(client, "first@test.com")
    client.post(f"/api/patterns/{first_pattern['id']}/publish")
    client.post("/api/logout")

    _login(client, "second@test.com")
    # Blocked while first's copy is still public.
    conflict = client.post(f"/api/patterns/{second_pattern['id']}/publish")
    assert conflict.status_code == 409
    client.post("/api/logout")

    _login(client, "first@test.com")
    client.post(f"/api/patterns/{first_pattern['id']}/unpublish")
    client.post("/api/logout")

    _login(client, "second@test.com")
    resp = client.post(f"/api/patterns/{second_pattern['id']}/publish")
    assert resp.status_code == 200
    assert resp.get_json()["pattern"]["is_public"] is True


# --- delete ------------------------------------------------------------

def test_delete_pattern_removes_it_and_cascades(client, app):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    pid = pattern["id"]

    _register(client, "friend")
    client.post(f"/api/patterns/{pid}/shares", json={"username": "friend"})
    client.patch(f"/api/patterns/{pid}/progress", json={"part": "Part 1", "index": 0, "completed": True})

    resp = client.delete(f"/api/patterns/{pid}")
    assert resp.status_code == 200

    with app.app_context():
        assert Pattern.query.get(pid) is None
        assert PatternShare.query.filter_by(pattern_id=pid).count() == 0
        assert UserPatternProgress.query.filter_by(pattern_id=pid).count() == 0

    assert client.get(f"/api/patterns/{pid}").status_code == 404


def test_only_uploader_or_admin_can_delete_not_an_edit_share(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    _login(client, _register(client, "editor"))
    client.post("/api/logout")

    _login(client, "owner@test.com")
    client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "editor", "can_edit": True})
    client.post("/api/logout")

    _login(client, "editor@test.com")
    resp = client.delete(f"/api/patterns/{pattern['id']}")
    assert resp.status_code == 403


# --- edit-level sharing --------------------------------------------------

def test_share_with_can_edit_grants_edit_access(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    _login(client, _register(client, "editor"))
    client.post("/api/logout")

    _login(client, "owner@test.com")
    resp = client.post(
        f"/api/patterns/{pattern['id']}/shares", json={"username": "editor", "can_edit": True}
    )
    assert resp.status_code == 201
    assert resp.get_json()[0]["can_edit"] is True
    client.post("/api/logout")

    _login(client, "editor@test.com")
    edit_resp = client.patch(
        f"/api/patterns/{pattern['id']}",
        json={"title": "Edited by editor", "instructions": pattern["instructions"]},
    )
    assert edit_resp.status_code == 200
    # But an edit-level share still can't manage sharing/publishing.
    assert client.post(f"/api/patterns/{pattern['id']}/publish").status_code == 403


def test_view_only_share_cannot_edit(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    _login(client, _register(client, "viewer"))
    client.post("/api/logout")

    _login(client, "owner@test.com")
    client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "viewer"})
    client.post("/api/logout")

    _login(client, "viewer@test.com")
    resp = client.patch(
        f"/api/patterns/{pattern['id']}",
        json={"title": "Hacked", "instructions": pattern["instructions"]},
    )
    assert resp.status_code == 403


def test_updating_share_permission_upgrades_view_to_edit(client, app):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    _register(client, "viewer")
    with app.app_context():
        viewer_id = User.query.filter_by(email="viewer@test.com").first().id
    client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "viewer"})

    resp = client.patch(f"/api/patterns/{pattern['id']}/shares/{viewer_id}", json={"can_edit": True})
    assert resp.status_code == 200
    shares = resp.get_json()
    assert next(s for s in shares if s["user_id"] == viewer_id)["can_edit"] is True


def test_updating_a_nonexistent_share_404s(client, app):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)
    _register(client, "stranger")
    with app.app_context():
        stranger_id = User.query.filter_by(email="stranger@test.com").first().id

    resp = client.patch(f"/api/patterns/{pattern['id']}/shares/{stranger_id}", json={"can_edit": True})
    assert resp.status_code == 404


# --- already_shared_with_you preview warning ----------------------------

def test_preview_flags_a_url_already_shared_with_you(client, app):
    url = "https://example.com/someone-elses-pattern"
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client, url=url, title="Owner's pattern")
    _register(client, "friend")
    with app.app_context():
        friend_id = User.query.filter_by(email="friend@test.com").first().id
    client.post(f"/api/patterns/{pattern['id']}/shares", json={"username": "friend"})
    client.post("/api/logout")

    _login(client, "friend@test.com")
    # Import a small ScraperError-free path is hard without network, so
    # instead confirm the flag comes through submit's duplicate check
    # doesn't block it, and preview's own field via /preview would need a
    # real scrape -- exercised instead through the shared helper directly.
    from app.patterns.routes import _shared_pattern_id
    with app.app_context():
        assert _shared_pattern_id(url, friend_id) == pattern["id"]
        assert _shared_pattern_id(url, 999999) is None
