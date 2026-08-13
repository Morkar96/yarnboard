"""
Tests for the manual pattern-photo upload/remove/stream endpoints
(POST/DELETE/GET /api/patterns/<id>/photo). Covers both sources a photo
can come from -- a scraped photo_url persisted at /submit time, and a
manually-uploaded one -- and confirms upload always replaces whichever was
there before (see Pattern.to_dict's priority rule in models.py).
"""

import io

from PIL import Image

from app.extensions import db
from app.models import User


def _register(client, username):
    email = f"{username}@test.com"
    resp = client.post(
        "/api/register",
        json={"username": username, "email": email, "password": "password123"},
    )
    assert resp.status_code == 201
    # Registration leaves the account unverified (see auth/routes.py); tests
    # log in right after, so fast-forward verification directly in the DB
    # rather than parsing the token out of a logged/sent email.
    with client.application.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_verified = True
        db.session.commit()
    return email


def _login(client, email):
    resp = client.post("/api/login", json={"email": email, "password": "password123"})
    assert resp.status_code == 200


def _submit_pattern(client, url="https://example.com/pattern", photo_url=None):
    resp = client.post(
        "/api/patterns/submit",
        json={
            "original_url": url,
            "title": "Test Pattern",
            "materials": "Yarn",
            "abbreviations": "k: knit",
            "instructions": {"Part 1": ["Cast on 10.", "Knit 5 rows."]},
            "photo_url": photo_url,
        },
    )
    assert resp.status_code == 201
    return resp.get_json()["pattern"]


def _make_admin(app, email):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.is_admin = True
        db.session.commit()


def _fake_photo_bytes(size=(50, 50), color=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _upload(client, pattern_id, filename="photo.png", data=None):
    return client.post(
        f"/api/patterns/{pattern_id}/photo",
        data={"photo": (io.BytesIO(data or _fake_photo_bytes()), filename)},
        content_type="multipart/form-data",
    )


def test_submit_persists_scraped_photo_url(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client, photo_url="https://cdn.example.com/found.jpg")

    assert pattern["has_photo"] is True
    assert pattern["photo_url"] == "https://cdn.example.com/found.jpg"


def test_upload_photo_replaces_scraped_url_and_serves_via_own_route(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client, photo_url="https://cdn.example.com/found.jpg")

    resp = _upload(client, pattern["id"])
    assert resp.status_code == 200
    updated = resp.get_json()["pattern"]
    assert updated["has_photo"] is True
    assert updated["photo_url"] == f"/api/patterns/{pattern['id']}/photo"

    stream = client.get(f"/api/patterns/{pattern['id']}/photo")
    assert stream.status_code == 200
    assert stream.content_type == "image/jpeg"
    assert len(stream.data) > 0


def test_uploading_again_replaces_previous_upload(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    _upload(client, pattern["id"], data=_fake_photo_bytes(color=(10, 10, 10)))
    first = client.get(f"/api/patterns/{pattern['id']}/photo").data

    _upload(client, pattern["id"], data=_fake_photo_bytes(color=(250, 250, 250)))
    second = client.get(f"/api/patterns/{pattern['id']}/photo").data

    assert first != second


def test_delete_photo_clears_both_scraped_and_uploaded_fields(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client, photo_url="https://cdn.example.com/found.jpg")
    _upload(client, pattern["id"])

    resp = client.delete(f"/api/patterns/{pattern['id']}/photo")
    assert resp.status_code == 200
    updated = resp.get_json()["pattern"]
    assert updated["has_photo"] is False
    assert updated["photo_url"] is None

    stream = client.get(f"/api/patterns/{pattern['id']}/photo")
    assert stream.status_code == 404


def test_upload_rejects_oversized_photo(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    from app import photo as photo_module

    oversized = b"\x00" * (photo_module.MAX_UPLOAD_BYTES + 1)
    resp = _upload(client, pattern["id"], data=oversized)
    assert resp.status_code == 400


def test_upload_rejects_non_image_bytes(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    resp = _upload(client, pattern["id"], filename="not-a-photo.txt", data=b"just some text, not an image")
    assert resp.status_code == 400


def test_non_owner_non_admin_cannot_upload_or_delete_photo(client):
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    other_email = _register(client, "other")
    _login(client, other_email)

    assert _upload(client, pattern["id"]).status_code == 403
    assert client.delete(f"/api/patterns/{pattern['id']}/photo").status_code == 403


def test_admin_can_upload_photo_on_any_pattern(app, client):
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)
    client.post("/api/logout")

    admin_email = _register(client, "admin")
    _make_admin(app, admin_email)
    _login(client, admin_email)

    resp = _upload(client, pattern["id"])
    assert resp.status_code == 200


def test_photo_upload_requires_login(client):
    resp = _upload(client, 1)
    assert resp.status_code == 401


def test_get_photo_returns_404_when_no_photo_uploaded(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    resp = client.get(f"/api/patterns/{pattern['id']}/photo")
    assert resp.status_code == 404
