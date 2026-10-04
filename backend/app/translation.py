"""
Pattern content translation between Hebrew and English, via Google's
Gemini API (https://ai.google.dev/api/generate-content).

Uses `requests` directly against the REST endpoint rather than the
`google-generativeai` PyPI package -- same "one POST, not worth a new
dependency" rationale as email.py's Resend integration.

Unlike email.py's "log instead of send when unset" fallback, a missing
GEMINI_API_KEY here raises immediately: a translation the caller is
actively waiting on (and will persist to the database) has no reasonable
"pretend it worked" no-op, unlike a best-effort notification email.

Two directions, two public entry points -- translate_pattern_to_hebrew
and translate_pattern_to_english -- since a pattern's own primary content
isn't always English (see scraper.py's Hebrew keyword support): a
Hebrew-sourced pattern needs an English overlay the same way an
English-sourced one needs a Hebrew overlay. Both share _call_gemini (the
actual HTTP call, retry, and response-shape handling, none of which is
direction-specific) and _build_translated_instructions (turning Gemini's
positional response back into a part-name-keyed dict); only the prompt
text and the target language's field-name suffix differ between them.
"""

import json
import os
import time
from pathlib import Path

import requests

# Hand-maintained corrections, e.g. {"dc": "עמוד כפול"} -- edit this file
# directly (English term -> exact Hebrew translation) whenever a reviewer
# flags a term Gemini got wrong or inconsistent; picked up on the very
# next translate call, no redeploy/restart needed. See
# _build_glossary_section for how it's fed into the prompt. English-
# target translation doesn't use this: standard English crochet/knitting
# abbreviations (sc/dc/hdc/ch/...) are already unambiguous, so there's no
# equivalent terminology-drift risk to hand-correct for that direction.
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
# Gemini occasionally 503s under load (seen directly in production) --
# retried automatically rather than failing the whole translate request
# on a transient blip. A 4xx (bad request, invalid key, etc.) is never
# retried -- that's not going to succeed on a second attempt, it'll just
# make the caller wait longer to see the same error.
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2

# Schema Gemini must respond in -- one instructions entry per input part,
# in the same order, so _build_translated_instructions can re-associate
# each translated entry with the part name it came from purely by
# position within this one response (see that function for why the
# *returned* structure is then re-keyed by the original part name rather
# than trusting anything Gemini calls it).
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

_PROMPT_TEMPLATE_TO_HEBREW = """\
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

_PROMPT_TEMPLATE_TO_ENGLISH = """\
You are translating a crochet/knitting pattern from Hebrew to English. \
Translate every field below into natural, correct English. Use standard \
English crochet/knitting stitch abbreviations (e.g. sc, dc, hdc, ch, sl \
st) rather than spelling out or transliterating the Hebrew stitch names. \
Preserve the exact structure: return exactly the same number of \
instruction entries, in the same order, with exactly the same number of \
steps in each entry as given below -- only translate the text itself.

Pattern JSON:
{pattern_json}
"""


class TranslationError(Exception):
    """Raised when a pattern couldn't be translated: missing API key, a
    failed API call, malformed glossary file, or a response that doesn't
    match the input structure (wrong part/step counts) -- see
    translate_pattern_to_hebrew/translate_pattern_to_english."""


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


def _call_gemini(prompt: str) -> dict:
    """
    POST `prompt` to Gemini and return the parsed {title, materials,
    abbreviations, instructions} response object -- the actual HTTP call,
    retry-on-transient-failure, and response-shape handling, shared by
    both translation directions (see module docstring). Raises
    TranslationError if GEMINI_API_KEY isn't set, every retry is
    exhausted, or the response doesn't parse into the expected shape.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise TranslationError(
            "GEMINI_API_KEY is not set -- cannot translate. See README for setup."
        )

    url = GEMINI_API_URL_TEMPLATE.format(model=GEMINI_MODEL)
    response = None
    for attempt in range(MAX_RETRIES + 1):
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
            break
        except requests.RequestException as exc:
            # A 4xx won't succeed on retry (bad request, invalid key,
            # etc.) -- fail immediately instead of burning the retry
            # budget on something that can't change.
            is_client_error = exc.response is not None and 400 <= exc.response.status_code < 500
            if is_client_error or attempt == MAX_RETRIES:
                raise TranslationError(
                    f"Gemini API request failed: {str(exc).replace(api_key, '<redacted>')}"
                ) from exc
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))

    try:
        raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(raw_text)
    except (KeyError, IndexError, ValueError) as exc:
        raise TranslationError(f"Gemini returned an unexpected response shape: {exc}") from exc


def _build_translated_instructions(
    parts: list[tuple[str, list[str]]], translated_parts: list[dict], field_suffix: str
) -> dict:
    """
    Zip Gemini's positional `instructions` response back onto the
    original part names, validating part/step counts match along the way
    (a mismatch is a translation bug worth failing loudly on, not
    something to silently paper over -- see instructions_he/instructions_en's
    docstrings in models.py for why the key-preservation contract matters
    at all: checklist progress is keyed by the pattern's own primary part
    names, regardless of which language is displayed).

    `field_suffix` is "he" or "en" -- picks between {"heading_he":
    "steps_he": ...} and {"heading_en": "steps_en": ...} in the output,
    matching whichever of Pattern.instructions_he/instructions_en this
    call is populating.
    """
    if len(translated_parts) != len(parts):
        raise TranslationError(
            f"Translation returned {len(translated_parts)} instruction parts, "
            f"expected {len(parts)}."
        )

    result = {}
    for (part_name, steps), translated_part in zip(parts, translated_parts):
        translated_steps = translated_part.get("steps") or []
        if len(translated_steps) != len(steps):
            raise TranslationError(
                f"Translation returned {len(translated_steps)} steps for "
                f"'{part_name}', expected {len(steps)}."
            )
        result[part_name] = {
            f"heading_{field_suffix}": translated_part.get("heading") or part_name,
            f"steps_{field_suffix}": translated_steps,
        }
    return result


def translate_pattern_to_hebrew(
    title: str, materials: str | None, abbreviations: str | None, instructions: dict
) -> tuple[str, str | None, str | None, dict]:
    """
    Translate a pattern's (primary, presumed-English) content to Hebrew
    in a single API call -- one call rather than one per field, so stitch
    terminology stays consistent across the whole pattern and the
    part/step structure can be mirrored back exactly instead of
    translated piecemeal.

    `instructions` is the same {part_name: [step, ...]} shape stored on
    Pattern.instructions. Returns (title_he, materials_he,
    abbreviations_he, instructions_he), where instructions_he is keyed by
    the *same* part_name strings passed in -- never Gemini's own Hebrew
    heading text -- see Pattern.instructions_he's docstring in models.py.
    """
    parts = list(instructions.items())
    pattern_for_model = {
        "title": title or "",
        "materials": materials or "",
        "abbreviations": abbreviations or "",
        "instructions": [{"heading": name, "steps": steps} for name, steps in parts],
    }
    glossary_section = _build_glossary_section(_load_glossary())
    prompt = _PROMPT_TEMPLATE_TO_HEBREW.format(
        glossary_section=glossary_section,
        pattern_json=json.dumps(pattern_for_model, ensure_ascii=False, indent=2),
    )

    translated = _call_gemini(prompt)
    try:
        translated_parts = translated["instructions"]
    except KeyError as exc:
        raise TranslationError(f"Gemini returned an unexpected response shape: {exc}") from exc

    instructions_he = _build_translated_instructions(parts, translated_parts, "he")
    return (
        translated.get("title") or title,
        translated.get("materials") or materials,
        translated.get("abbreviations") or abbreviations,
        instructions_he,
    )


def translate_pattern_to_english(
    title: str, materials: str | None, abbreviations: str | None, instructions: dict
) -> tuple[str, str | None, str | None, dict]:
    """
    The reverse of translate_pattern_to_hebrew: translates a pattern's
    (primary, presumed-Hebrew) content to English in a single API call --
    for a pattern scraped from a Hebrew-language source page (see
    scraper.py's Hebrew keyword support), which needs an English overlay
    the same way an English-sourced pattern needs a Hebrew one.

    Returns (title_en, materials_en, abbreviations_en, instructions_en),
    with the same part-name-key-preservation contract as the Hebrew
    direction -- see Pattern.instructions_en's docstring in models.py.
    Doesn't use translation_glossary.json (see that file's docstring for
    why the English direction doesn't need one).
    """
    parts = list(instructions.items())
    pattern_for_model = {
        "title": title or "",
        "materials": materials or "",
        "abbreviations": abbreviations or "",
        "instructions": [{"heading": name, "steps": steps} for name, steps in parts],
    }
    prompt = _PROMPT_TEMPLATE_TO_ENGLISH.format(
        pattern_json=json.dumps(pattern_for_model, ensure_ascii=False, indent=2),
    )

    translated = _call_gemini(prompt)
    try:
        translated_parts = translated["instructions"]
    except KeyError as exc:
        raise TranslationError(f"Gemini returned an unexpected response shape: {exc}") from exc

    instructions_en = _build_translated_instructions(parts, translated_parts, "en")
    return (
        translated.get("title") or title,
        translated.get("materials") or materials,
        translated.get("abbreviations") or abbreviations,
        instructions_en,
    )
