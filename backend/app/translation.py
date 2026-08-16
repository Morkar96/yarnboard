"""
Hebrew translation of pattern content, via Google's Gemini API
(https://ai.google.dev/api/generate-content).

Uses `requests` directly against the REST endpoint rather than the
`google-generativeai` PyPI package -- same "one POST, not worth a new
dependency" rationale as email.py's Resend integration.

Unlike email.py's "log instead of send when unset" fallback, a missing
GEMINI_API_KEY here raises immediately: a translation the caller is
actively waiting on (and will persist to the database) has no reasonable
"pretend it worked" no-op, unlike a best-effort notification email.
"""

import json
import os
from pathlib import Path

import requests

# Hand-maintained corrections, e.g. {"dc": "עמוד כפול"} -- edit this file
# directly (English term -> exact Hebrew translation) whenever a reviewer
# flags a term Gemini got wrong or inconsistent; picked up on the very
# next translate call, no redeploy/restart needed. See
# _build_glossary_section for how it's fed into the prompt.
GLOSSARY_PATH = Path(__file__).parent / "translation_glossary.json"

GEMINI_API_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
# A version-less alias, deliberately -- pinned model names get deprecated
# and start 404ing for new callers on a timeline outside this app's
# control (confirmed directly against the API during development: a
# pinned "gemini-2.5-flash" was already rejected with "no longer
# available to new users"). "-latest" trades a small amount of
# translation-output stability for not silently breaking down the line.
GEMINI_MODEL = "gemini-flash-latest"
REQUEST_TIMEOUT_SECONDS = 60

# Schema Gemini must respond in -- one instructions entry per input part,
# in the same order, so translate_pattern_to_hebrew can re-associate each
# translated entry with the English part name it came from purely by
# position within this one response (see that function for why the
# *returned* structure is then re-keyed by the original English part name
# rather than trusting anything Gemini calls it).
_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "materials": {"type": "STRING"},
        "abbreviations": {"type": "STRING"},
        "instructions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "heading": {"type": "STRING"},
                    "steps": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["heading", "steps"],
            },
        },
    },
    "required": ["title", "materials", "abbreviations", "instructions"],
}

_PROMPT_TEMPLATE = """\
You are translating a crochet/knitting pattern from English to Hebrew for \
Israeli crafters. Translate every field below into natural, correct \
Hebrew. Use standard Israeli crochet/knitting terminology for stitch \
names and abbreviations (e.g. single crochet, double crochet, chain, \
slip stitch) -- do not leave English abbreviations like 'sc'/'dc'/'ch' \
untranslated, and do not invent terminology that isn't standard. \
Preserve the exact structure: return exactly the same number of \
instruction entries, in the same order, with exactly the same number of \
steps in each entry as given below -- only translate the text itself.
{glossary_section}
Pattern JSON:
{pattern_json}
"""


class TranslationError(Exception):
    """Raised when a pattern couldn't be translated: missing API key, a
    failed API call, malformed glossary file, or a response that doesn't
    match the input structure (wrong part/step counts) -- see
    translate_pattern_to_hebrew."""


def _load_glossary() -> dict[str, str]:
    """Re-read translation_glossary.json on every call (rather than once
    at import time) so edits to it take effect on the next translate
    request without a server restart."""
    if not GLOSSARY_PATH.exists():
        return {}
    try:
        with GLOSSARY_PATH.open(encoding="utf-8") as f:
            glossary = json.load(f)
    except (OSError, ValueError) as exc:
        raise TranslationError(f"translation_glossary.json is invalid: {exc}") from exc
    if not isinstance(glossary, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in glossary.items()
    ):
        raise TranslationError("translation_glossary.json must be a flat object of string: string")
    return glossary


def _build_glossary_section(glossary: dict[str, str]) -> str:
    if not glossary:
        return ""
    lines = "\n".join(f'- "{term}" -> "{hebrew}"' for term, hebrew in glossary.items())
    return (
        "\nUse exactly these Hebrew translations for the following terms "
        "whenever they appear, overriding your own judgment -- these are "
        f"confirmed corrections from a native-speaker review:\n{lines}\n"
    )


def translate_pattern_to_hebrew(
    title: str, materials: str | None, abbreviations: str | None, instructions: dict
) -> tuple[str, str | None, str | None, dict]:
    """
    Translate a pattern's English content to Hebrew in a single API call
    -- one call rather than one per field, so stitch terminology stays
    consistent across the whole pattern and the part/step structure can
    be mirrored back exactly instead of translated piecemeal.

    `instructions` is the same {part_name: [step, ...]} shape stored on
    Pattern.instructions. Returns (title_he, materials_he,
    abbreviations_he, instructions_he), where instructions_he is keyed by
    the *same* part_name strings passed in -- never Gemini's own Hebrew
    heading text -- because checklist progress (UserPatternProgress,
    toggle_progress in patterns/routes.py) is keyed by the English part
    name; see Pattern.instructions_he's docstring in models.py.

    Raises TranslationError if GEMINI_API_KEY isn't set, the API call
    fails, or the response's part/step counts don't match the input
    (a mismatch here is a translation bug worth failing loudly on, not
    something to silently paper over).
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise TranslationError(
            "GEMINI_API_KEY is not set -- cannot translate. See README for setup."
        )

    parts = list(instructions.items())
    pattern_for_model = {
        "title": title or "",
        "materials": materials or "",
        "abbreviations": abbreviations or "",
        "instructions": [{"heading": name, "steps": steps} for name, steps in parts],
    }
    glossary_section = _build_glossary_section(_load_glossary())
    prompt = _PROMPT_TEMPLATE.format(
        glossary_section=glossary_section,
        pattern_json=json.dumps(pattern_for_model, ensure_ascii=False, indent=2),
    )

    url = GEMINI_API_URL_TEMPLATE.format(model=GEMINI_MODEL)
    try:
        response = requests.post(
            url,
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": _RESPONSE_SCHEMA,
                },
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise TranslationError(f"Gemini API request failed: {exc}") from exc

    try:
        raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        translated = json.loads(raw_text)
        translated_parts = translated["instructions"]
    except (KeyError, IndexError, ValueError) as exc:
        raise TranslationError(f"Gemini returned an unexpected response shape: {exc}") from exc

    if len(translated_parts) != len(parts):
        raise TranslationError(
            f"Translation returned {len(translated_parts)} instruction parts, "
            f"expected {len(parts)}."
        )

    instructions_he = {}
    for (part_name, steps), translated_part in zip(parts, translated_parts):
        translated_steps = translated_part.get("steps") or []
        if len(translated_steps) != len(steps):
            raise TranslationError(
                f"Translation returned {len(translated_steps)} steps for "
                f"'{part_name}', expected {len(steps)}."
            )
        instructions_he[part_name] = {
            "heading_he": translated_part.get("heading") or part_name,
            "steps_he": translated_steps,
        }

    return (
        translated.get("title") or title,
        translated.get("materials") or materials,
        translated.get("abbreviations") or abbreviations,
        instructions_he,
    )
