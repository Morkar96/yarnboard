# Swap Gemini pattern translation for Azure AI Translator (free tier)

## Context

Pattern translation (`backend/app/translation.py`) currently goes
through Gemini's `generateContent` API: one call per direction
(`translate_pattern_to_hebrew` / `translate_pattern_to_english`) sends
the whole pattern (title, materials, abbreviations, and every
instruction part/step) as one structured-JSON prompt, and Gemini
returns a matching structured JSON object back — a real LLM call, not a
plain string translator. This was hit by a transient `503 Service
Unavailable` from Gemini during dev-backend testing (already retried
automatically per `MAX_RETRIES`/`RETRY_BACKOFF_SECONDS` in
`_call_gemini`, and it's a known, occasional, already-handled failure
mode per that function's own comment — not a recurring blocker today).
The user asked what a free-tier alternative would look like in case
Gemini's cost/quota/reliability ever becomes a real problem.

**This is a real architecture change, not a key swap.** Gemini is doing
two things a plain translation API doesn't do:
1. Whole-document context in one call, so stitch terminology stays
   consistent across the whole pattern (per `translate_pattern_to_hebrew`'s
   docstring: "one call rather than one per field... so stitch
   terminology stays consistent").
2. Instruction-following on top of translation — e.g. "use standard
   Israeli crochet terminology, don't leave `sc`/`dc`/`ch` untranslated,
   don't invent terminology," and the glossary override
   (`translation_glossary.json` via `_build_glossary_section`) that
   forces specific term corrections regardless of the model's own
   judgment.

**Azure AI Translator** (`api.cognitive.microsoft.com`) is the best
free-tier fit for this specific need: 2,000,000 characters/month free,
*forever* (not a trial), and — unlike DeepL's free tier, which doesn't
support Hebrew at all — it supports `he` as both a source and target
language. It's a plain statistical/neural translator, not an LLM, so
(1) above is preserved differently (see below) and (2) is only
partially preservable via its "Dynamic Dictionary" feature.

## Key differences from the Gemini integration

- **Request shape**: Azure's `Translate` operation takes a JSON array
  of `{"Text": "..."}` objects and translates every element in one
  HTTP call, returning translations in the same order — so the
  "one call, not one per field" property Gemini gives us can still be
  kept, just via array batching instead of a single structured-JSON
  object. Flatten `[title, materials, abbreviations, *all instruction
  steps]` into one array per call, keeping an index map back to
  `(part_name, step_index)` / `title` / `materials` / `abbreviations`
  to reassemble the response — replaces `_RESPONSE_SCHEMA` and the
  Gemini-specific `responseSchema`/`responseMimeType` config entirely.
- **Structure preservation is automatic, not model-obeyed**: Azure
  returns exactly one translation per input string, in order — the
  part/step-count mismatch that `_build_translated_instructions`
  currently guards against (a case where Gemini disobeys the "same
  structure" instruction) becomes structurally impossible with Azure,
  since we're the ones building the array 1:1. That validation logic
  can be deleted, not adapted.
- **Glossary**: Azure supports inline per-request term overrides via a
  `<mstrans:dictionary translation="...">source</mstrans:dictionary>`
  markup tag embedded directly in the source text (not a separate API
  parameter) — a real analog to `_build_glossary_section`, but only for
  single-word-or-short-phrase exact matches; can't express "override
  the model's own judgment" the way a free-text instruction can.
- **Auth**: `Ocp-Apim-Subscription-Key` + `Ocp-Apim-Subscription-Region`
  headers, not Gemini's `?key=` query param — two new env vars
  (`AZURE_TRANSLATOR_KEY`, `AZURE_TRANSLATOR_REGION`) instead of one.
- **Error shape**: Azure returns `{"error": {"code": <int>, "message":
  "..."}}` on failure, with Microsoft-specific numeric codes (e.g.
  `400036` for an unsupported language pair) rather than Gemini's HTTP
  status alone — `_call_gemini`'s `is_client_error` 4xx/5xx retry split
  still applies at the HTTP-status level, but the redacted-key error
  message and any code-specific handling need rewriting against Azure's
  codes, not Gemini's.
- **What's lost**: terminology *consistency reasoning* across a whole
  pattern (Azure translates each string independently, with no
  cross-string context — two occurrences of an ambiguous term could in
  theory come back inconsistently, something Gemini's single-context
  call avoids by construction) and free-text instruction-following
  ("don't invent terminology," Israeli-specific phrasing preferences)
  beyond what the dynamic dictionary can pin down term-by-term.

## What's needed

### 1. Account & credentials (one-time, outside the codebase)
- Azure account + a Translator resource (free `F0` tier) created in the
  Azure Portal — no credit card-free option exists for Azure signup
  itself, but the `F0` tier stays free up to the 2M char/month cap.
- Note the resource's key and region (e.g. `eastus`) for the two new
  env vars below.

### 2. Backend changes (`backend/app/translation.py`)
- New constants replacing `GEMINI_API_URL_TEMPLATE`/`GEMINI_MODEL`:
  `AZURE_TRANSLATOR_ENDPOINT = "https://api.cognitive.microsofttranslator.com/translate"`,
  `AZURE_API_VERSION = "3.0"`.
- Rewrite `_call_gemini` (rename to `_call_azure_translate` or similar)
  to: build the flattened `[{"Text": ...}, ...]` array, POST with
  `params={"api-version": "3.0", "from": source_lang, "to": target_lang}`
  and the two auth headers, keep the existing retry/backoff loop
  (same shape, different exception-to-error-code mapping), then
  re-assemble the flat translated-text array back into
  `{title, materials, abbreviations, instructions: [...]}` using the
  index map built before the call.
- Delete `_RESPONSE_SCHEMA` (no schema concept in Azure's API) and the
  count-mismatch checks in `_build_translated_instructions` (see above
  — structurally guaranteed instead).
- Rewrite `_build_glossary_section` to emit the `<mstrans:dictionary>`
  inline markup per matched term instead of a prompt-text list; still
  reads from the same `translation_glossary.json` file/format, so no
  change needed there.
- `translate_pattern_to_hebrew`/`translate_pattern_to_english`'s
  signatures and return shapes stay identical — this keeps
  `patterns/routes.py`'s two call sites (`routes.py:902`, `:968`) and
  `TranslationError` handling (`:907`, `:973`) completely unchanged,
  since both are the actual integration surface with the rest of the
  app.
- `README.md`'s Gemini setup note and `.env`/`render.yaml` references
  to `GEMINI_API_KEY` need the equivalent Azure env var documentation.

### 3. Config / deployment
- New env vars everywhere `GEMINI_API_KEY` is currently set: local
  `.env`, `render.yaml` (`sync: false` entries), CI's `ci.yml` e2e job
  (blanked the same way `GEMINI_API_KEY: ""` is today, to keep e2e
  tests from making real translation calls).
- `backend/tests/test_pattern_translation.py`'s `monkeypatch.setenv`
  calls (lines 303/352/371/388) and its mocked-response fixtures need
  rewriting against Azure's request/response shape instead of Gemini's
  — the test *behavior* (missing key raises, 5xx retries, 4xx doesn't,
  malformed response raises) stays the same, only the mocked payloads
  change.

## Open decision (not resolved by this sketch)

Whether to fully replace Gemini or keep it as a fallback (try Gemini
first, fall back to Azure on repeated failure) — the code shape above
assumes a full replacement for simplicity. A dual-provider fallback is
possible but roughly doubles the surface area (two auth schemes, two
error-handling paths, a decision for which one "wins" on quality
differences) for a problem (occasional Gemini 503s) that's already
mitigated by the existing retry logic. Recommend against building the
fallback unless Gemini reliability becomes a recurring, not
occasional, problem.

## Critical files
- `backend/app/translation.py` — the entire rewrite described above.
- `backend/app/translation_glossary.json` — format unchanged, only how
  it's rendered into the request changes.
- `backend/tests/test_pattern_translation.py` — mocked API
  request/response fixtures need rewriting.
- `render.yaml`, `.github/workflows/ci.yml`, `README.md` — env var
  references.
- `backend/app/patterns/routes.py` — no changes expected (only if the
  fallback-vs-replace decision above lands on "keep both").

## Verification
- **Automated**: `backend/tests/test_pattern_translation.py` after its
  fixtures are rewritten — same assertions (missing-key error,
  retry-then-succeed, 4xx-fails-fast, malformed-response error,
  part/step structure preserved) should still hold against Azure's
  mocked responses.
- **Manual**: translate a real pattern with known ambiguous
  terminology (something already flagged in
  `translation_glossary.json`) in both directions, confirm the dynamic
  dictionary override actually takes effect, and spot-check that a
  term appearing twice in the same pattern translates consistently
  both times (the specific risk called out above from losing
  whole-document context).
