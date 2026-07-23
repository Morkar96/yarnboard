"""
Tests for the pattern-editing permission model (_can_edit) and the
version-based per-user progress-staleness mechanism (see
UserPatternProgress's docstring in app/models.py for the full design).
This is the logic a prior PR review flagged as having no test coverage.
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
    return email


def _login(client, email):
    resp = client.post("/api/login", json={"email": email, "password": "password123"})
    assert resp.status_code == 200


def _submit_pattern(client, url="https://example.com/pattern"):
    resp = client.post(
        "/api/patterns/submit",
        json={
            "original_url": url,
            "title": "Test Pattern",
            "materials": "Yarn",
            "abbreviations": "k: knit",
            "instructions": {"Part 1": ["Cast on 10.", "Knit 5 rows."]},
        },
    )
    assert resp.status_code == 201
    return resp.get_json()["pattern"]


def _make_admin(app, email):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.is_admin = True
        db.session.commit()


def test_owner_can_edit_own_pattern(client):
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)

    resp = client.patch(
        f"/api/patterns/{pattern['id']}",
        json={"title": "Updated Title", "instructions": pattern["instructions"]},
    )
    assert resp.status_code == 200
    assert resp.get_json()["pattern"]["title"] == "Updated Title"


def test_non_owner_non_admin_cannot_edit(client):
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    other_email = _register(client, "other")
    _login(client, other_email)
    resp = client.patch(
        f"/api/patterns/{pattern['id']}",
        json={"title": "Hacked", "instructions": {"Part 1": ["x"]}},
    )
    assert resp.status_code == 403


def test_admin_can_edit_any_pattern(app, client):
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    admin_email = _register(client, "admin")
    _make_admin(app, admin_email)
    _login(client, admin_email)

    resp = client.patch(
        f"/api/patterns/{pattern['id']}",
        json={"title": "Admin Edit", "instructions": {"Part 1": ["x"]}},
    )
    assert resp.status_code == 200
    assert resp.get_json()["pattern"]["title"] == "Admin Edit"


def test_edit_without_permission_leaves_pattern_unchanged(client):
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    other_email = _register(client, "other")
    _login(client, other_email)
    client.patch(
        f"/api/patterns/{pattern['id']}",
        json={"title": "Hacked", "instructions": {"Part 1": ["x"]}},
    )
    client.post("/api/logout")

    _login(client, owner_email)
    detail = client.get(f"/api/patterns/{pattern['id']}").get_json()
    assert detail["title"] == "Test Pattern"


def test_toggle_progress_then_edit_stales_progress_until_acknowledged(app, client):
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)
    pattern_id = pattern["id"]
    client.post("/api/logout")

    other_email = _register(client, "other")
    _login(client, other_email)
    resp = client.patch(
        f"/api/patterns/{pattern_id}/progress",
        json={"part": "Part 1", "index": 0, "completed": True},
    )
    assert resp.status_code == 200

    detail = client.get(f"/api/patterns/{pattern_id}").get_json()
    assert detail["instructions"]["Part 1"][0]["completed"] is True
    client.post("/api/logout")

    # Owner edits the instructions -- this is a real content change, so it
    # must bump instructions_version and stale the other user's progress.
    _login(client, owner_email)
    resp = client.patch(
        f"/api/patterns/{pattern_id}",
        json={
            "title": "Test Pattern",
            "instructions": {"Part 1": ["Cast on 10.", "Knit 5 rows.", "Bind off."]},
        },
    )
    assert resp.status_code == 200
    client.post("/api/logout")

    _login(client, other_email)
    detail = client.get(f"/api/patterns/{pattern_id}").get_json()
    assert detail["instructions"]["Part 1"][0]["completed"] is False

    notifications = client.get("/api/patterns/notifications").get_json()
    assert any(n["id"] == pattern_id for n in notifications)

    # Acknowledging clears the stale progress row immediately, rather than
    # waiting for the user's next checkbox click.
    ack = client.post(f"/api/patterns/{pattern_id}/acknowledge-update")
    assert ack.status_code == 200
    notifications = client.get("/api/patterns/notifications").get_json()
    assert not any(n["id"] == pattern_id for n in notifications)


def test_editing_instructions_with_no_real_change_does_not_bump_version(app, client):
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)
    pattern_id = pattern["id"]

    resp = client.patch(
        f"/api/patterns/{pattern_id}",
        json={"title": "Test Pattern", "instructions": {"Part 1": ["Cast on 10.", "Knit 5 rows."]}},
    )
    assert resp.status_code == 200

    with app.app_context():
        refreshed = Pattern.query.get(pattern_id)
        assert refreshed.instructions_version == 1


def test_toggle_progress_rejects_invalid_step_reference(client):
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)

    resp = client.patch(
        f"/api/patterns/{pattern['id']}/progress",
        json={"part": "Nonexistent Part", "index": 0, "completed": True},
    )
    assert resp.status_code == 400

    resp = client.patch(
        f"/api/patterns/{pattern['id']}/progress",
        json={"part": "Part 1", "index": 99, "completed": True},
    )
    assert resp.status_code == 400
