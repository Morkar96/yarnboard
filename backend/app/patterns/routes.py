"""
Pattern endpoints: scrape-preview, submit/publish, edit, the three list
views (mine / saved / community), pattern detail, per-user checklist
progress, and change notifications.

Endpoints that matter most for correctness:
  - POST /preview never writes to the database -- it's pure "show me what
    you'd get" so the user can review before publishing.
  - POST /submit is the only endpoint that creates a Pattern row, and it
    re-checks the URL uniqueness right before inserting (in addition to the
    DB-level unique constraint) so two near-simultaneous submissions of the
    same URL can't both succeed.
  - PATCH /<id> is the only endpoint that edits a published Pattern row.
    Editing `instructions` invalidates other users' checklist progress on
    it (see UserPatternProgress.pattern_version's docstring in models.py);
    this endpoint, toggle_progress, and /acknowledge-update are the three
    places that version field is read or written -- see each one's
    docstring for its specific rule about when it's allowed to write.
"""

from flask import Blueprint, Response, current_app, request, jsonify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from .. import photo, translation
from ..email import send_pattern_updated_email
from ..extensions import db
from ..models import Pattern, User, UserPatternProgress
from ..scraper import parse_pattern_html, parse_pattern_pdf, scrape_pattern_from_url, ScraperError
from ..utils import get_current_user_id

patterns_bp = Blueprint("patterns", __name__, url_prefix="/api/patterns")


def _require_login():
    """Return (user_id, None) or (None, error_response) for route guards."""
    user_id = get_current_user_id()
    if not user_id:
        return None, (jsonify({"error": "Unauthorized", "code": "unauthorized"}), 401)
    return user_id, None


def _can_edit(user: User, pattern: Pattern) -> bool:
    """Admins can edit any pattern; everyone else only their own uploads."""
    return user.is_admin or pattern.uploader_id == user.id


def _validate_instructions_he(instructions: dict, instructions_he) -> str | None:
    """
    Returns an error message if `instructions_he` doesn't structurally
    mirror `instructions` -- same part-name keys (never translated keys
    of its own), and each part's steps_he the same length as its English
    steps. Returns None if valid.

    This invariant is what lets checklist progress (keyed by the English
    part name -- see UserPatternProgress's docstring and toggle_progress
    below) stay correct regardless of which language is displayed; see
    Pattern.instructions_he's docstring in models.py for the full
    rationale. A mismatch here is a translation bug, not a legitimate
    structural edit -- reject it rather than silently accepting content
    that would desync from the checklist.
    """
    if not isinstance(instructions_he, dict):
        return "instructions_he must be an object keyed by part name."
    if set(instructions_he.keys()) != set(instructions.keys()):
        return "instructions_he must have exactly the same part names as instructions."
    for part, steps in instructions.items():
        entry = instructions_he[part]
        if not isinstance(entry, dict):
            return f"instructions_he['{part}'] must be an object with heading_he/steps_he."
        steps_he = entry.get("steps_he")
        if not isinstance(steps_he, list) or len(steps_he) != len(steps):
            return f"instructions_he['{part}']['steps_he'] must have {len(steps)} entries."
    return None


def _existing_pattern_response(url: str):
    """If `url` is already published, the short-circuit response for
    /preview and /preview-upload alike: duplicate=True plus its id, so the
    frontend can offer "view the existing pattern" instead of a review
    form for content that would just fail to save later. Returns None if
    there's no existing pattern for this URL."""
    existing = Pattern.query.filter_by(original_url=url).first()
    if not existing:
        return None
    return jsonify({
        "duplicate": True,
        "existing_pattern_id": existing.id,
        "draft": None,
    }), 200


@patterns_bp.route("/preview", methods=["POST"])
def preview_pattern():
    """
    Scrape `url` and return a draft for the user to review -- no DB write.
    """
    user_id, error = _require_login()
    if error:
        return error

    url = (request.get_json(silent=True) or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required", "code": "url_required"}), 400

    duplicate_response = _existing_pattern_response(url)
    if duplicate_response:
        return duplicate_response

    try:
        draft = scrape_pattern_from_url(url)
    except ScraperError as exc:
        # No fixed translation key for this one -- the message itself is
        # server-generated and varies per failure (bot-detection, timeout,
        # unparseable page, etc.), not a fixed string a resource file could
        # localize. The frontend shows it as-is regardless of UI language;
        # "scraper_error" just tells it not to look up a translation key.
        return jsonify({"error": str(exc), "code": "scraper_error"}), 502

    return jsonify({"duplicate": False, "existing_pattern_id": None, "draft": draft}), 200


@patterns_bp.route("/preview-upload", methods=["POST"])
def preview_pattern_from_upload():
    """
    Like /preview, but the page's content comes from a file the user
    uploaded instead of being fetched by the server -- either a saved
    HTML page or a PDF (e.g. a paid Etsy/Ravelry pattern distributed as a
    PDF, which Yarnboard has no way to "fetch" at all).

    This is also the fallback for sites whose bot-detection (e.g.
    Cloudflare's JS challenge -- see scraper.ScraperError messages) blocks
    Yarnboard's automatic fetch entirely: the user opens the page in their
    own browser, saves it, and uploads the saved HTML here. `url` is still
    required and still used for dedup and attribution in both cases --
    only the content used for extraction is user-supplied instead of
    fetched by us.

    Which parser runs is decided by sniffing the file's own bytes (a
    `%PDF-` magic header), not by filename extension or the browser-
    supplied Content-Type -- both of those are just claims the client
    makes about the file, not verified facts about it.

    multipart/form-data body: `url` (text field), `html_file` (file field,
    despite the name also accepts a PDF).
    """
    user_id, error = _require_login()
    if error:
        return error

    url = (request.form.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url is required", "code": "url_required"}), 400

    uploaded = request.files.get("html_file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "html_file is required", "code": "file_required"}), 400

    duplicate_response = _existing_pattern_response(url)
    if duplicate_response:
        return duplicate_response

    raw_bytes = uploaded.read()

    try:
        if raw_bytes.startswith(b"%PDF-"):
            draft = parse_pattern_pdf(raw_bytes, url)
        else:
            html = raw_bytes.decode("utf-8", errors="replace")
            draft = parse_pattern_html(html, url)
    except ScraperError as exc:
        # See preview_pattern's identical case above for why this is a
        # raw message + a generic "don't translate this" code, not a
        # fixed translation key.
        return jsonify({"error": str(exc), "code": "scraper_error"}), 502

    return jsonify({"duplicate": False, "existing_pattern_id": None, "draft": draft}), 200


@patterns_bp.route("/submit", methods=["POST"])
def submit_pattern():
    """
    Save a user-reviewed draft as a published Pattern.

    Expects the (possibly hand-edited) fields the /preview draft contained,
    plus original_url. This is the only place a Pattern row gets created --
    publishing only happens once a human has confirmed the content.
    """
    user_id, error = _require_login()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    original_url = (data.get("original_url") or "").strip()
    title = (data.get("title") or "").strip()
    if not original_url or not title:
        return jsonify({
            "error": "original_url and title are required",
            "code": "missing_fields",
        }), 400

    if Pattern.query.filter_by(original_url=original_url).first():
        return jsonify({
            "error": "A pattern from this URL already exists.",
            "code": "pattern_already_exists",
        }), 409

    pattern = Pattern(
        original_url=original_url,
        title=title,
        author=(data.get("author") or None),
        source_site_name=data.get("source_site_name") or Pattern.derive_source_domain(original_url),
        source_domain=data.get("source_domain") or Pattern.derive_source_domain(original_url),
        materials=data.get("materials"),
        abbreviations=data.get("abbreviations"),
        instructions=data.get("instructions") or {},
        photo_url=(data.get("photo_url") or None),
        photo_source=("scraped" if data.get("photo_url") else None),
        uploader_id=user_id,
    )
    db.session.add(pattern)
    try:
        db.session.commit()
    except IntegrityError:
        # Race: another request inserted the same original_url between our
        # check above and this commit. The unique constraint caught it.
        db.session.rollback()
        return jsonify({
            "error": "A pattern from this URL already exists.",
            "code": "pattern_already_exists",
        }), 409

    return jsonify({
        "message": "Pattern successfully published to the Yarnboard community.",
        "pattern": pattern.to_dict(current_user_id=user_id),
    }), 201


@patterns_bp.route("/<int:pattern_id>", methods=["PATCH"])
def edit_pattern(pattern_id):
    """
    Edit a published pattern. Admins can edit any pattern; everyone else
    only their own uploads (see _can_edit).

    Accepts title/author/materials/abbreviations/instructions -- anything
    else in the body (original_url, source_site_name, source_domain) is
    silently ignored rather than validated, since those fields must stay
    immutable for dedup and attribution integrity.

    If `instructions` actually changes (compared before reassigning, so
    this is a real content diff, not a self-comparison), bumps
    instructions_version and emails everyone with meaningful progress on
    this pattern (see _notify_progress_users) -- this is what the
    per-user staleness mechanism in UserPatternProgress keys off of.

    Optionally also accepts title_he/materials_he/abbreviations_he/
    instructions_he -- present only when the uploader/an admin is
    correcting the auto-translation (see POST /<id>/translate), never
    required. Providing `instructions_he` (even as an explicit `{}`, e.g.
    to clear a translation) is what signals "this request is editing the
    Hebrew content"; omitting it entirely leaves any existing translation
    untouched. A Hebrew-content edit sets translation_reviewed = True (an
    edit *is* the review) but deliberately does NOT bump
    instructions_version or notify anyone -- that mechanism is about the
    canonical English structure changing shape, not a translation
    correction.
    """
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_edit(user, pattern):
        return jsonify({
            "error": "You don't have permission to edit this pattern.",
            "code": "edit_forbidden",
        }), 403

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required", "code": "title_required"}), 400

    new_instructions = data.get("instructions") or {}
    instructions_changed = new_instructions != (pattern.instructions or {})

    if "instructions_he" in data:
        instructions_he = data.get("instructions_he") or {}
        validation_error = _validate_instructions_he(new_instructions, instructions_he)
        if validation_error:
            # Raw message, not a fixed key -- see the scraper_error cases
            # above for the same reasoning (this text names the specific
            # part/step count that's wrong, generated per-request).
            return jsonify({"error": validation_error, "code": "invalid_translation"}), 400

    pattern.title = title
    pattern.author = data.get("author") or None
    pattern.materials = data.get("materials")
    pattern.abbreviations = data.get("abbreviations")
    pattern.instructions = new_instructions
    if instructions_changed:
        pattern.instructions_version += 1

    if "instructions_he" in data:
        pattern.title_he = (data.get("title_he") or "").strip() or None
        pattern.materials_he = data.get("materials_he")
        pattern.abbreviations_he = data.get("abbreviations_he")
        pattern.instructions_he = instructions_he
        pattern.translation_reviewed = True

    db.session.commit()

    if instructions_changed:
        _notify_progress_users(pattern, editor_user_id=user_id)

    return jsonify({
        "message": "Pattern updated.",
        "pattern": pattern.to_dict(current_user_id=user_id),
    }), 200


@patterns_bp.route("/<int:pattern_id>/translate", methods=["POST"])
def translate_pattern(pattern_id):
    """
    Auto-translate this pattern's content to Hebrew via Gemini (see
    ../translation.py) and persist it as an unreviewed draft. No-ops
    (returns the pattern unchanged) if a translation already exists --
    translation happens once per pattern, never overwriting an existing
    one (including a human-reviewed one) on every request; to redo it, an
    uploader/admin edits the Hebrew fields directly via PATCH /<id>
    instead.

    Any logged-in user can trigger this, not just the pattern's uploader
    -- translating doesn't change the pattern's authoritative English
    content, so it doesn't need the stricter _can_edit permission that
    editing/photo routes use.
    """
    user_id, error = _require_login()
    if error:
        return error

    pattern = Pattern.query.get_or_404(pattern_id)
    if pattern.title_he:
        return jsonify({
            "message": "This pattern already has a Hebrew translation.",
            "pattern": pattern.to_dict(current_user_id=user_id),
        }), 200

    try:
        title_he, materials_he, abbreviations_he, instructions_he = (
            translation.translate_pattern_to_hebrew(
                pattern.title, pattern.materials, pattern.abbreviations,
                pattern.instructions or {},
            )
        )
    except translation.TranslationError as exc:
        return jsonify({"error": str(exc), "code": "translation_error"}), 502

    pattern.title_he = title_he
    pattern.materials_he = materials_he
    pattern.abbreviations_he = abbreviations_he
    pattern.instructions_he = instructions_he
    pattern.translation_reviewed = False
    db.session.commit()

    return jsonify({
        "message": "Pattern translated to Hebrew.",
        "pattern": pattern.to_dict(current_user_id=user_id),
    }), 200


@patterns_bp.route("/<int:pattern_id>/photo", methods=["POST"])
def upload_pattern_photo(pattern_id):
    """
    Upload (or replace) the "photo of the finished object" on an already-
    published pattern -- works the same whether this pattern already had a
    scraped photo, a previously-uploaded one, or none at all. Same
    permission rule as editing the pattern's text (_can_edit): admins can
    do this on any pattern, everyone else only their own uploads.

    multipart/form-data body: `photo` (file field). The raw upload is
    capped tighter than the global MAX_CONTENT_LENGTH (see photo.py's
    MAX_UPLOAD_BYTES) so the error message is accurate for a photo
    specifically, then normalized (downscaled, re-encoded as JPEG,
    stripped of EXIF) by photo.process_upload before being stored --
    see that module's docstring for why.

    A successful upload always replaces any scraped photo_url this pattern
    had (photo_data takes priority in Pattern.to_dict) -- manual upload is
    meant to override, not layer behind, whatever scraping found.
    """
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_edit(user, pattern):
        return jsonify({
            "error": "You don't have permission to edit this pattern.",
            "code": "edit_forbidden",
        }), 403

    uploaded = request.files.get("photo")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "photo is required", "code": "file_required"}), 400

    raw_bytes = uploaded.read()
    if len(raw_bytes) > photo.MAX_UPLOAD_BYTES:
        max_mb = photo.MAX_UPLOAD_BYTES // (1024 * 1024)
        # code alone isn't enough to localize this one -- the limit
        # (max_mb) is interpolated, so a translated string needs it too;
        # the frontend passes {max_mb} into the "file_too_large" key's
        # translation rather than just swapping in a fixed string.
        return jsonify({
            "error": f"That photo is too large (max {max_mb}MB).",
            "code": "file_too_large",
            "max_mb": max_mb,
        }), 400

    try:
        processed = photo.process_upload(raw_bytes)
    except photo.PhotoError as exc:
        return jsonify({"error": str(exc), "code": "photo_error"}), 400

    pattern.photo_data = processed
    pattern.photo_content_type = "image/jpeg"
    pattern.photo_source = "uploaded"
    pattern.photo_url = None
    db.session.commit()

    return jsonify({
        "message": "Photo updated.",
        "pattern": pattern.to_dict(current_user_id=user_id),
    }), 200


@patterns_bp.route("/<int:pattern_id>/photo", methods=["DELETE"])
def delete_pattern_photo(pattern_id):
    """
    Remove this pattern's photo entirely -- whether it came from scraping
    or a manual upload. Deliberately clears both sources rather than
    "falling back" to a previously-scraped photo_url after an uploaded one
    is removed -- that would be surprising; "remove the photo" should mean
    no photo, full stop. Same permission rule as upload/edit (_can_edit).
    """
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_edit(user, pattern):
        return jsonify({
            "error": "You don't have permission to edit this pattern.",
            "code": "edit_forbidden",
        }), 403

    pattern.photo_data = None
    pattern.photo_content_type = None
    pattern.photo_source = None
    pattern.photo_url = None
    db.session.commit()

    return jsonify({
        "message": "Photo removed.",
        "pattern": pattern.to_dict(current_user_id=user_id),
    }), 200


@patterns_bp.route("/<int:pattern_id>/photo", methods=["GET"])
def get_pattern_photo(pattern_id):
    """
    Stream a manually-uploaded photo's raw bytes. No login required --
    pattern detail (GET /<id>) is already public, so its photo is too.
    Only ever the target of Pattern.to_dict()'s "photo_url" field when
    photo_data is actually set (a scraped photo_url points straight at the
    external source site instead, never through this route) -- so a 404
    here means the frontend is acting on stale data, not something to
    paper over by falling back to anything else.
    """
    pattern = Pattern.query.get_or_404(pattern_id)
    if not pattern.photo_data:
        return jsonify({"error": "This pattern has no uploaded photo.", "code": "no_photo"}), 404

    return Response(pattern.photo_data, mimetype=pattern.photo_content_type or "image/jpeg")


def _notify_progress_users(pattern: Pattern, editor_user_id: int) -> None:
    """
    Email everyone with meaningful checklist progress on `pattern` that it
    just changed. Called after instructions_version has already been
    bumped and committed. Best-effort per recipient -- one failed send
    (bad address, Resend outage) is logged and skipped, never rolls back
    the edit or blocks the remaining recipients.
    """
    progress_rows = UserPatternProgress.query.filter_by(pattern_id=pattern.id).all()
    for progress in progress_rows:
        if progress.user_id == editor_user_id:
            continue  # no self-notification for your own edit
        if not progress.has_any_completed_step():
            continue  # stale-but-empty progress isn't real engagement
        try:
            send_pattern_updated_email(progress.user.email, pattern)
        except Exception:
            current_app.logger.exception(
                "Failed to send pattern-updated email to user %s for pattern %s",
                progress.user_id, pattern.id,
            )


@patterns_bp.route("/notifications", methods=["GET"])
def pattern_notifications():
    """
    Patterns the current user has meaningful, now-stale progress on --
    drives the in-app "this pattern changed" banner. Read-only: unlike
    /acknowledge-update, viewing this list doesn't clear anything.
    """
    user_id, error = _require_login()
    if error:
        return error

    stale = (
        db.session.query(Pattern, UserPatternProgress)
        .join(UserPatternProgress, UserPatternProgress.pattern_id == Pattern.id)
        .filter(
            UserPatternProgress.user_id == user_id,
            UserPatternProgress.pattern_version < Pattern.instructions_version,
        )
        .all()
    )
    return jsonify([
        {"id": pattern.id, "title": pattern.title}
        for pattern, progress in stale
        if progress.has_any_completed_step()
    ]), 200


@patterns_bp.route("/<int:pattern_id>/acknowledge-update", methods=["POST"])
def acknowledge_pattern_update(pattern_id):
    """
    Dismiss the "this pattern changed" banner for one pattern, clearing
    this user's now-stale checklist progress on it immediately (rather
    than waiting for their next checkbox click, see toggle_progress).

    Re-checks staleness before writing anything -- if it's not actually
    stale anymore (e.g. a duplicate call from a second browser tab that
    already lazily reset via toggle_progress), this is a no-op rather than
    wiping progress the user may have already re-entered.
    """
    user_id, error = _require_login()
    if error:
        return error

    pattern = Pattern.query.get_or_404(pattern_id)
    progress = UserPatternProgress.query.filter_by(
        user_id=user_id, pattern_id=pattern_id
    ).first()

    if progress and progress.pattern_version < pattern.instructions_version:
        progress.completed_steps = {}
        progress.pattern_version = pattern.instructions_version
        db.session.commit()

    return jsonify({"message": "Acknowledged."}), 200


@patterns_bp.route("/mine", methods=["GET"])
def my_uploaded_patterns():
    """Patterns this user personally uploaded."""
    user_id, error = _require_login()
    if error:
        return error

    patterns = Pattern.query.filter_by(uploader_id=user_id).order_by(Pattern.created_at.desc()).all()
    return jsonify([p.to_dict(current_user_id=user_id) for p in patterns]), 200


@patterns_bp.route("/saved", methods=["GET", "POST"])
def my_saved_patterns():
    """List this user's bookmarked community patterns, or bookmark a new one."""
    user_id, error = _require_login()
    if error:
        return error
    user = User.query.get(user_id)

    if request.method == "POST":
        pattern_id = (request.get_json(silent=True) or {}).get("pattern_id")
        pattern = Pattern.query.get(pattern_id)
        if not pattern:
            return jsonify({"error": "Pattern not found", "code": "pattern_not_found"}), 404
        if pattern not in user.saved_patterns:
            user.saved_patterns.append(pattern)
            db.session.commit()
        return jsonify({"message": f"Pattern '{pattern.title}' saved."}), 200

    return jsonify([p.to_dict(current_user_id=user_id) for p in user.saved_patterns]), 200


@patterns_bp.route("/saved/<int:pattern_id>", methods=["DELETE"])
def unsave_pattern(pattern_id):
    """Remove a pattern from this user's saved/bookmarked list."""
    user_id, error = _require_login()
    if error:
        return error
    user = User.query.get(user_id)

    pattern = Pattern.query.get(pattern_id)
    if pattern and pattern in user.saved_patterns:
        user.saved_patterns.remove(pattern)
        db.session.commit()

    return jsonify({"message": "Pattern removed from saved list."}), 200


@patterns_bp.route("/community", methods=["GET"])
def community_patterns():
    """All published patterns, newest first. Public -- unregistered visitors
    can browse the community library, same as a single pattern's detail
    view (get_pattern below); to_dict() already renders progress-free
    output when there's no logged-in user to look progress up for."""
    user_id = get_current_user_id()

    patterns = Pattern.query.order_by(Pattern.created_at.desc()).all()
    return jsonify([p.to_dict(current_user_id=user_id) for p in patterns]), 200


@patterns_bp.route("/<int:pattern_id>", methods=["GET"])
def get_pattern(pattern_id):
    """A single pattern's full detail, including this viewer's checklist
    progress if they're logged in."""
    user_id = get_current_user_id()
    pattern = Pattern.query.get_or_404(pattern_id)
    return jsonify(pattern.to_dict(current_user_id=user_id)), 200


@patterns_bp.route("/<int:pattern_id>/progress", methods=["PATCH"])
def toggle_progress(pattern_id):
    """
    Flip a single checklist step for the current user only.

    Body: {"part": <part name>, "index": <step index within that part>,
    "completed": <bool>}. Get-or-creates this user's UserPatternProgress
    row for the pattern, then mutates completed_steps[part][index]. Because
    completed_steps is a JSON column, SQLAlchemy can't see in-place mutation
    of the nested dict/list on its own -- flag_modified tells it to persist
    the change on commit (without it, the UPDATE would silently be a no-op).

    A new row is stamped with the pattern's *current* instructions_version
    (never left at the column default) -- otherwise a pattern edited
    several times before this user's first-ever checkbox click would look
    falsely stale immediately. An existing row that IS stale (the pattern
    was edited since this user last touched it) is wiped before the new
    toggle is applied -- this is the lazy per-user reset described in
    UserPatternProgress's docstring, triggered by real interaction rather
    than a bulk operation at edit time.
    """
    user_id, error = _require_login()
    if error:
        return error

    pattern = Pattern.query.get_or_404(pattern_id)
    data = request.get_json(silent=True) or {}
    part = data.get("part")
    index = data.get("index")
    completed = bool(data.get("completed"))

    if part is None or index is None or part not in (pattern.instructions or {}):
        return jsonify({
            "error": "part and index must reference a valid step",
            "code": "invalid_progress_step",
        }), 400

    step_count = len(pattern.instructions[part])
    if not isinstance(index, int) or not (0 <= index < step_count):
        return jsonify({
            "error": "index out of range for this part",
            "code": "invalid_progress_step",
        }), 400

    progress = UserPatternProgress.query.filter_by(
        user_id=user_id, pattern_id=pattern_id
    ).first()
    if progress is None:
        progress = UserPatternProgress(
            user_id=user_id,
            pattern_id=pattern_id,
            completed_steps={},
            pattern_version=pattern.instructions_version,
        )
        db.session.add(progress)
    elif progress.pattern_version < pattern.instructions_version:
        progress.completed_steps = {}
        progress.pattern_version = pattern.instructions_version

    flags = progress.completed_steps.get(part) or [False] * step_count
    # Pad defensively in case the part's step count differs from what's
    # already recorded (shouldn't normally happen now that stale rows are
    # wiped above, but cheap to guard against regardless).
    if len(flags) < step_count:
        flags = flags + [False] * (step_count - len(flags))
    flags[index] = completed

    progress.completed_steps[part] = flags
    flag_modified(progress, "completed_steps")
    db.session.commit()

    return jsonify({"completed_steps": progress.completed_steps}), 200
