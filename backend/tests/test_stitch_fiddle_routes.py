"""
Tests for the Stitch Fiddle link save/list/remove/import endpoints
(backend/app/stitch_fiddle/routes.py). stitchfiddle.fetch_chart is
monkeypatched throughout -- it's the one function in this app that would
otherwise require real Playwright/network access, and this suite runs
without either (same boundary test_pattern_photo_routes.py draws around
Pillow-processed bytes rather than real uploaded files from a browser).
"""

import json
from pathlib import Path

from app import stitchfiddle
from app.extensions import db
from app.models import Pattern, User

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "stitchfiddle-chart-response.json").read_text()
)
CHART = FIXTURE["state"]["chart"]
SIZE = CHART["grid"]["settings"]["size"]

REAL_SHARE_URL = "https://www.stitchfiddle.com/c/so1rbr-bw0bk4"


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


def _make_admin(app, email):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.is_admin = True
        db.session.commit()


def _fake_successful_chart(*_args, **_kwargs):
    return {
        "title": CHART["settings"]["title"],
        "chart_id": CHART["settings"]["chartId"],
        "column_count": SIZE["columnCount"],
        "row_count": SIZE["rowCount"],
        "palette": CHART["palette"]["styles"],
        "grid_rows_field": CHART["grid"]["rows"],
    }


def _fake_access_denied(*_args, **_kwargs):
    raise stitchfiddle.StitchFiddleError(
        "This chart isn't public. In Stitch Fiddle, open the chart's "
        "Share settings and set access to Public, then try again."
    )


def _save_link(client, share_url=REAL_SHARE_URL):
    resp = client.post("/api/stitch-fiddle/links", json={"share_url": share_url})
    assert resp.status_code in (200, 201)
    return resp.get_json()


def test_save_link_rejects_non_stitchfiddle_url(client):
    _login(client, _register(client, "owner"))

    resp = client.post("/api/stitch-fiddle/links", json={"share_url": "https://example.com/x"})
    assert resp.status_code == 400


def test_save_list_and_delete_link(client):
    _login(client, _register(client, "owner"))

    saved = _save_link(client)
    assert saved["chart_id"] == "so1rbr-bw0bk4"
    assert saved["imported_pattern_id"] is None

    listed = client.get("/api/stitch-fiddle/links").get_json()
    assert [link["id"] for link in listed] == [saved["id"]]

    resp = client.delete(f"/api/stitch-fiddle/links/{saved['id']}")
    assert resp.status_code == 200
    assert client.get("/api/stitch-fiddle/links").get_json() == []


def test_saving_the_same_chart_twice_returns_existing_row_not_a_duplicate(client):
    _login(client, _register(client, "owner"))

    first = _save_link(client)
    second = _save_link(client)

    assert first["id"] == second["id"]
    assert len(client.get("/api/stitch-fiddle/links").get_json()) == 1


def test_import_creates_pattern_with_chart_grid(client, monkeypatch):
    monkeypatch.setattr(stitchfiddle, "fetch_chart", _fake_successful_chart)
    _login(client, _register(client, "owner"))
    link = _save_link(client)

    resp = client.post(f"/api/stitch-fiddle/links/{link['id']}/import")
    assert resp.status_code == 201
    pattern = resp.get_json()["pattern"]
    assert pattern["title"] == CHART["settings"]["title"]
    assert "Color 1" in pattern["materials"]

    grid = pattern["chart_grid"]
    assert grid is not None
    assert grid["column_count"] == SIZE["columnCount"]
    assert grid["row_count"] == SIZE["rowCount"]
    assert len(grid["cells"]) == SIZE["columnCount"] * SIZE["rowCount"]
    assert len(grid["palette"]) == len(CHART["palette"]["styles"])

    with client.application.app_context():
        db_pattern = Pattern.query.get(pattern["id"])
        assert db_pattern.original_url == REAL_SHARE_URL

    updated_link = client.get("/api/stitch-fiddle/links").get_json()[0]
    assert updated_link["imported_pattern_id"] == pattern["id"]


def test_reimporting_an_already_imported_link_is_a_noop(client, monkeypatch):
    monkeypatch.setattr(stitchfiddle, "fetch_chart", _fake_successful_chart)
    _login(client, _register(client, "owner"))
    link = _save_link(client)
    client.post(f"/api/stitch-fiddle/links/{link['id']}/import")

    resp = client.post(f"/api/stitch-fiddle/links/{link['id']}/import")
    assert resp.status_code == 200
    assert resp.get_json()["message"] == "Already imported."

    with client.application.app_context():
        assert Pattern.query.filter_by(original_url=REAL_SHARE_URL).count() == 1


def test_importing_a_url_already_published_by_someone_else_links_instead_of_duplicating(
    client, monkeypatch
):
    monkeypatch.setattr(stitchfiddle, "fetch_chart", _fake_successful_chart)
    other_email = _register(client, "other")
    _login(client, other_email)
    client.post(
        "/api/patterns/submit",
        json={
            "original_url": REAL_SHARE_URL,
            "title": "Manually submitted already",
            "instructions": {},
        },
    )
    client.post("/api/logout")

    _login(client, _register(client, "owner"))
    link = _save_link(client)
    resp = client.post(f"/api/stitch-fiddle/links/{link['id']}/import")

    assert resp.status_code == 200
    assert resp.get_json()["pattern"]["title"] == "Manually submitted already"
    with client.application.app_context():
        assert Pattern.query.filter_by(original_url=REAL_SHARE_URL).count() == 1


def test_import_surfaces_access_denied_as_a_clear_error(client, monkeypatch):
    monkeypatch.setattr(stitchfiddle, "fetch_chart", _fake_access_denied)
    _login(client, _register(client, "owner"))
    link = _save_link(client)

    resp = client.post(f"/api/stitch-fiddle/links/{link['id']}/import")
    assert resp.status_code == 502
    assert "Public" in resp.get_json()["error"]

    with client.application.app_context():
        assert Pattern.query.count() == 0


def test_non_owner_cannot_delete_or_import_someone_elses_link(client, monkeypatch):
    monkeypatch.setattr(stitchfiddle, "fetch_chart", _fake_successful_chart)
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    link = _save_link(client)
    client.post("/api/logout")

    _login(client, _register(client, "other"))
    assert client.delete(f"/api/stitch-fiddle/links/{link['id']}").status_code == 403
    assert client.post(f"/api/stitch-fiddle/links/{link['id']}/import").status_code == 403


def test_links_endpoints_require_login(client):
    assert client.get("/api/stitch-fiddle/links").status_code == 401
    resp = client.post("/api/stitch-fiddle/links", json={"share_url": REAL_SHARE_URL})
    assert resp.status_code == 401
