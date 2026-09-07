"""
Tests for Hebrew pattern translation: POST /<id>/translate and PATCH
/<id>'s optional Hebrew-content editing (backend/app/patterns/routes.py,
backend/app/translation.py). translation.translate_pattern_to_hebrew is
monkeypatched throughout -- it's a real Gemini API call, same boundary
test_stitch_fiddle_routes.py draws around stitchfiddle.fetch_chart.
"""

import json

import pytest

from app import translation
from app.extensions import db
from app.models import Pattern, User

INSTRUCTIONS = {
    "Part 1: Cast On": ["Cast on 10.", "Knit 1 row."],
    "Part 2: Body": ["Knit 5 rows.", "Purl 5 rows.", "Bind off."],
}


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


def _submit_pattern(client, instructions=None):
    resp = client.post(
        "/api/patterns/submit",
        json={
            "original_url": "https://example.com/pattern",
            "title": "Test Pattern",
            "materials": "Yarn",
            "abbreviations": "k: knit",
            "instructions": instructions if instructions is not None else INSTRUCTIONS,
        },
    )
    assert resp.status_code == 201
    return resp.get_json()["pattern"]


def _fake_translate(title, materials, abbreviations, instructions):
    """Deterministic stand-in for translation.translate_pattern_to_hebrew --
    prefixes every string with a marker so tests can assert it actually
    ran, and mirrors the real function's key-preserving contract."""
    instructions_he = {
        part: {"heading_he": f"HE:{part}", "steps_he": [f"HE:{s}" for s in steps]}
        for part, steps in instructions.items()
    }
    return f"HE:{title}", f"HE:{materials}", f"HE:{abbreviations}", instructions_he


def test_translate_populates_hebrew_fields_unreviewed(client, monkeypatch):
    monkeypatch.setattr(translation, "translate_pattern_to_hebrew", _fake_translate)
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    resp = client.post(f"/api/patterns/{pattern['id']}/translate")
    assert resp.status_code == 200
    translated = resp.get_json()["pattern"]["translations"]["he"]
    assert translated["title"] == "HE:Test Pattern"
    assert translated["materials"] == "HE:Yarn"
    assert translated["reviewed"] is False
    assert translated["instructions"]["Part 1: Cast On"]["steps_he"] == [
        "HE:Cast on 10.", "HE:Knit 1 row.",
    ]
    # Keys stay the English part names -- never translated -- so checklist
    # progress (keyed the same way) has something to attach to.
    assert set(translated["instructions"].keys()) == set(INSTRUCTIONS.keys())


def test_translate_is_noop_once_a_translation_exists(client, monkeypatch):
    calls = []

    def counting_translate(*args, **kwargs):
        calls.append(1)
        return _fake_translate(*args, **kwargs)

    monkeypatch.setattr(translation, "translate_pattern_to_hebrew", counting_translate)
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    client.post(f"/api/patterns/{pattern['id']}/translate")
    resp = client.post(f"/api/patterns/{pattern['id']}/translate")

    assert resp.status_code == 200
    assert len(calls) == 1
    assert "already has a Hebrew translation" in resp.get_json()["message"]


def test_translate_requires_login(client):
    resp = client.post("/api/patterns/1/translate")
    assert resp.status_code == 401


def test_translate_any_logged_in_user_can_trigger_it(client, monkeypatch):
    """Unlike editing, translating isn't gated by _can_edit -- it doesn't
    change the pattern's authoritative English content. It's still gated
    by _can_view though, so the pattern needs to actually be visible to
    "any" user -- published here, for exactly that reason."""
    monkeypatch.setattr(translation, "translate_pattern_to_hebrew", _fake_translate)
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)
    client.post(f"/api/patterns/{pattern['id']}/publish")

    other_email = _register(client, "other")
    _login(client, other_email)
    resp = client.post(f"/api/patterns/{pattern['id']}/translate")
    assert resp.status_code == 200
    assert resp.get_json()["pattern"]["translations"]["he"]["title"] == "HE:Test Pattern"


def test_translate_surfaces_translation_error_as_502(client, monkeypatch):
    def failing_translate(*args, **kwargs):
        raise translation.TranslationError("GEMINI_API_KEY is not set")

    monkeypatch.setattr(translation, "translate_pattern_to_hebrew", failing_translate)
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    resp = client.post(f"/api/patterns/{pattern['id']}/translate")
    assert resp.status_code == 502
    assert "GEMINI_API_KEY" in resp.get_json()["error"]


def test_edit_with_matching_instructions_he_marks_reviewed(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    instructions_he = {
        part: {"heading_he": f"HE:{part}", "steps_he": [f"HE:{s}" for s in steps]}
        for part, steps in INSTRUCTIONS.items()
    }
    resp = client.patch(
        f"/api/patterns/{pattern['id']}",
        json={
            "title": pattern["title"],
            "materials": pattern["materials"],
            "abbreviations": pattern["abbreviations"],
            "instructions": INSTRUCTIONS,
            "title_he": "HE:Test Pattern",
            "materials_he": "HE:Yarn",
            "abbreviations_he": "HE:k: knit",
            "instructions_he": instructions_he,
        },
    )
    assert resp.status_code == 200
    translated = resp.get_json()["pattern"]["translations"]["he"]
    assert translated["reviewed"] is True
    assert translated["title"] == "HE:Test Pattern"


def test_edit_rejects_instructions_he_with_wrong_part_names(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    resp = client.patch(
        f"/api/patterns/{pattern['id']}",
        json={
            "title": pattern["title"],
            "instructions": INSTRUCTIONS,
            "instructions_he": {"Some Other Part": {"heading_he": "x", "steps_he": ["a"]}},
        },
    )
    assert resp.status_code == 400
    assert "part names" in resp.get_json()["error"]


def test_edit_rejects_instructions_he_with_wrong_step_count(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    bad_instructions_he = {
        "Part 1: Cast On": {"heading_he": "x", "steps_he": ["only one step"]},
        "Part 2: Body": {"heading_he": "y", "steps_he": ["a", "b", "c"]},
    }
    resp = client.patch(
        f"/api/patterns/{pattern['id']}",
        json={
            "title": pattern["title"],
            "instructions": INSTRUCTIONS,
            "instructions_he": bad_instructions_he,
        },
    )
    assert resp.status_code == 400
    assert "Part 1: Cast On" in resp.get_json()["error"]


def test_editing_translation_does_not_bump_instructions_version_or_notify(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.patterns.routes.send_pattern_updated_email",
        lambda *a, **k: sent.append(1),
    )
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    with client.application.app_context():
        version_before = Pattern.query.get(pattern["id"]).instructions_version

    instructions_he = {
        part: {"heading_he": f"HE:{part}", "steps_he": [f"HE:{s}" for s in steps]}
        for part, steps in INSTRUCTIONS.items()
    }
    client.patch(
        f"/api/patterns/{pattern['id']}",
        json={
            "title": pattern["title"],
            "instructions": INSTRUCTIONS,
            "instructions_he": instructions_he,
        },
    )

    with client.application.app_context():
        version_after = Pattern.query.get(pattern["id"]).instructions_version
    assert version_after == version_before
    assert sent == []


def test_edit_translation_requires_same_permission_as_english_edit(client):
    owner_email = _register(client, "owner")
    _login(client, owner_email)
    pattern = _submit_pattern(client)

    other_email = _register(client, "other")
    _login(client, other_email)

    instructions_he = {
        part: {"heading_he": f"HE:{part}", "steps_he": [f"HE:{s}" for s in steps]}
        for part, steps in INSTRUCTIONS.items()
    }
    resp = client.patch(
        f"/api/patterns/{pattern['id']}",
        json={
            "title": pattern["title"],
            "instructions": INSTRUCTIONS,
            "instructions_he": instructions_he,
        },
    )
    assert resp.status_code == 403


class _FakeGeminiResponse:
    """Stand-in for requests.Response, just enough for
    translate_pattern_to_hebrew's raise_for_status()/json() calls."""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _gemini_payload(instructions):
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "title": "HE:title",
                                    "materials": "HE:materials",
                                    "abbreviations": "HE:abbrev",
                                    "instructions": [
                                        {"heading": f"HE:{name}", "steps": [f"HE:{s}" for s in steps]}
                                        for name, steps in instructions.items()
                                    ],
                                }
                            )
                        }
                    ]
                }
            }
        ]
    }


def test_glossary_terms_are_included_in_the_prompt_sent_to_gemini(monkeypatch, tmp_path):
    glossary_path = tmp_path / "glossary.json"
    glossary_path.write_text(json.dumps({"dc": "עמוד כפול"}), encoding="utf-8")
    monkeypatch.setattr(translation, "GLOSSARY_PATH", glossary_path)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    captured = {}

    def fake_post(url, params, json, timeout):
        captured["prompt"] = json["contents"][0]["parts"][0]["text"]
        return _FakeGeminiResponse(_gemini_payload(INSTRUCTIONS))

    monkeypatch.setattr(translation.requests, "post", fake_post)

    translation.translate_pattern_to_hebrew("Title", "Materials", "k: knit", INSTRUCTIONS)

    assert '"dc" -> "עמוד כפול"' in captured["prompt"]


def test_missing_glossary_file_produces_no_glossary_section(monkeypatch, tmp_path):
    monkeypatch.setattr(translation, "GLOSSARY_PATH", tmp_path / "does-not-exist.json")
    assert translation._load_glossary() == {}
    assert translation._build_glossary_section({}) == ""


def test_invalid_glossary_file_raises_translation_error(monkeypatch, tmp_path):
    glossary_path = tmp_path / "glossary.json"
    glossary_path.write_text("not valid json", encoding="utf-8")
    monkeypatch.setattr(translation, "GLOSSARY_PATH", glossary_path)

    with pytest.raises(translation.TranslationError):
        translation._load_glossary()


def test_glossary_file_must_be_a_flat_string_to_string_object(monkeypatch, tmp_path):
    glossary_path = tmp_path / "glossary.json"
    glossary_path.write_text(json.dumps({"dc": ["not", "a", "string"]}), encoding="utf-8")
    monkeypatch.setattr(translation, "GLOSSARY_PATH", glossary_path)

    with pytest.raises(translation.TranslationError):
        translation._load_glossary()


def _fake_response_error(status_code):
    """A requests.RequestException carrying a fake `.response.status_code`
    -- same shape as what raise_for_status() actually raises, without a
    real HTTP round trip."""
    return translation.requests.exceptions.RequestException(
        f"{status_code} error", response=type("R", (), {"status_code": status_code})()
    )


def test_translation_retries_on_transient_server_error_then_succeeds(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(translation, "RETRY_BACKOFF_SECONDS", 0)  # don't actually sleep in tests
    calls = {"count": 0}

    def fake_post(url, params, json, timeout):
        calls["count"] += 1
        if calls["count"] < 3:
            raise _fake_response_error(503)
        return _FakeGeminiResponse(_gemini_payload(INSTRUCTIONS))

    monkeypatch.setattr(translation.requests, "post", fake_post)

    title_he, *_ = translation.translate_pattern_to_hebrew("Title", "Materials", "k: knit", INSTRUCTIONS)

    assert title_he == "HE:title"
    assert calls["count"] == 3  # failed twice, succeeded on the 3rd attempt


def test_translation_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(translation, "RETRY_BACKOFF_SECONDS", 0)
    calls = {"count": 0}

    def fake_post(url, params, json, timeout):
        calls["count"] += 1
        raise _fake_response_error(503)

    monkeypatch.setattr(translation.requests, "post", fake_post)

    with pytest.raises(translation.TranslationError):
        translation.translate_pattern_to_hebrew("Title", "Materials", "k: knit", INSTRUCTIONS)

    assert calls["count"] == translation.MAX_RETRIES + 1


def _fake_translate_en(title, materials, abbreviations, instructions):
    """Deterministic stand-in for translation.translate_pattern_to_english
    -- the mirror of _fake_translate above, for the reverse direction."""
    instructions_en = {
        part: {"heading_en": f"EN:{part}", "steps_en": [f"EN:{s}" for s in steps]}
        for part, steps in instructions.items()
    }
    return f"EN:{title}", f"EN:{materials}", f"EN:{abbreviations}", instructions_en


def test_translate_to_english_populates_english_fields_unreviewed(client, monkeypatch):
    monkeypatch.setattr(translation, "translate_pattern_to_english", _fake_translate_en)
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    resp = client.post(f"/api/patterns/{pattern['id']}/translate-to-english")
    assert resp.status_code == 200
    translated = resp.get_json()["pattern"]["translations"]["en"]
    assert translated["title"] == "EN:Test Pattern"
    assert translated["materials"] == "EN:Yarn"
    assert translated["reviewed"] is False
    assert translated["instructions"]["Part 1: Cast On"]["steps_en"] == [
        "EN:Cast on 10.", "EN:Knit 1 row.",
    ]
    assert set(translated["instructions"].keys()) == set(INSTRUCTIONS.keys())
    # Translating in one direction never touches the other.
    assert resp.get_json()["pattern"]["translations"]["he"] is None


def test_translate_to_english_is_noop_once_a_translation_exists(client, monkeypatch):
    calls = []

    def counting_translate(*args, **kwargs):
        calls.append(1)
        return _fake_translate_en(*args, **kwargs)

    monkeypatch.setattr(translation, "translate_pattern_to_english", counting_translate)
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    client.post(f"/api/patterns/{pattern['id']}/translate-to-english")
    resp = client.post(f"/api/patterns/{pattern['id']}/translate-to-english")

    assert resp.status_code == 200
    assert len(calls) == 1
    assert "already has an English translation" in resp.get_json()["message"]


def test_translate_to_english_requires_login(client):
    resp = client.post("/api/patterns/1/translate-to-english")
    assert resp.status_code == 401


def test_translate_to_english_surfaces_translation_error_as_502(client, monkeypatch):
    def failing_translate(*args, **kwargs):
        raise translation.TranslationError("GEMINI_API_KEY is not set")

    monkeypatch.setattr(translation, "translate_pattern_to_english", failing_translate)
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    resp = client.post(f"/api/patterns/{pattern['id']}/translate-to-english")
    assert resp.status_code == 502
    assert "GEMINI_API_KEY" in resp.get_json()["error"]


def test_edit_with_matching_instructions_en_marks_en_reviewed(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    instructions_en = {
        part: {"heading_en": f"EN:{part}", "steps_en": [f"EN:{s}" for s in steps]}
        for part, steps in INSTRUCTIONS.items()
    }
    resp = client.patch(
        f"/api/patterns/{pattern['id']}",
        json={
            "title": pattern["title"],
            "instructions": INSTRUCTIONS,
            "title_en": "EN:Test Pattern",
            "instructions_en": instructions_en,
        },
    )
    assert resp.status_code == 200
    translated = resp.get_json()["pattern"]["translations"]["en"]
    assert translated["reviewed"] is True
    assert translated["title"] == "EN:Test Pattern"


def test_edit_rejects_instructions_en_with_wrong_part_names(client):
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    resp = client.patch(
        f"/api/patterns/{pattern['id']}",
        json={
            "title": pattern["title"],
            "instructions": INSTRUCTIONS,
            "instructions_en": {"Some Other Part": {"heading_en": "x", "steps_en": ["a"]}},
        },
    )
    assert resp.status_code == 400
    assert "part names" in resp.get_json()["error"]


def test_can_edit_hebrew_and_english_translations_independently_in_one_request(client):
    """Both _he and _en groups are accepted in the same PATCH, and don't
    interfere with each other -- a pattern can carry both translation
    directions at once."""
    _login(client, _register(client, "owner"))
    pattern = _submit_pattern(client)

    instructions_he = {
        part: {"heading_he": f"HE:{part}", "steps_he": [f"HE:{s}" for s in steps]}
        for part, steps in INSTRUCTIONS.items()
    }
    instructions_en = {
        part: {"heading_en": f"EN:{part}", "steps_en": [f"EN:{s}" for s in steps]}
        for part, steps in INSTRUCTIONS.items()
    }
    resp = client.patch(
        f"/api/patterns/{pattern['id']}",
        json={
            "title": pattern["title"],
            "instructions": INSTRUCTIONS,
            "title_he": "HE:Test Pattern",
            "instructions_he": instructions_he,
            "title_en": "EN:Test Pattern",
            "instructions_en": instructions_en,
        },
    )
    assert resp.status_code == 200
    translations = resp.get_json()["pattern"]["translations"]
    assert translations["he"]["title"] == "HE:Test Pattern"
    assert translations["en"]["title"] == "EN:Test Pattern"


def test_translation_does_not_retry_a_client_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(translation, "RETRY_BACKOFF_SECONDS", 0)
    calls = {"count": 0}

    def fake_post(url, params, json, timeout):
        calls["count"] += 1
        raise _fake_response_error(400)

    monkeypatch.setattr(translation.requests, "post", fake_post)

    with pytest.raises(translation.TranslationError):
        translation.translate_pattern_to_hebrew("Title", "Materials", "k: knit", INSTRUCTIONS)

    assert calls["count"] == 1  # no retries for a 4xx
