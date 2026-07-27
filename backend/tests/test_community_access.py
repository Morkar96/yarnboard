"""Regression test for GET /api/patterns/community: unregistered visitors
must not be able to browse the community pattern library at all."""


def _register_and_login(client, username):
    email = f"{username}@test.com"
    client.post(
        "/api/register",
        json={"username": username, "email": email, "password": "password123"},
    )
    client.post("/api/login", json={"email": email, "password": "password123"})


def test_community_patterns_requires_login(client):
    resp = client.get("/api/patterns/community")
    assert resp.status_code == 401


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
