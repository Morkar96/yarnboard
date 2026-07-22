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

from flask import Blueprint, current_app, request, jsonify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from ..email import send_pattern_updated_email
from ..extensions import db
from ..models import Pattern, User, UserPatternProgress
from ..scraper import parse_pattern_html, scrape_pattern_from_url, ScraperError
from ..utils import get_current_user_id

patterns_bp = Blueprint("patterns", __name__, url_prefix="/api/patterns")


def _require_login():
    """Return (user_id, None) or (None, error_response) for route guards."""
    user_id = get_current_user_id()
    if not user_id:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    return user_id, None


def _can_edit(user: User, pattern: Pattern) -> bool:
    """Admins can edit any pattern; everyone else only their own uploads."""
    return user.is_admin or pattern.uploader_id == user.id


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
        return jsonify({"error": "url is required"}), 400

    duplicate_response = _existing_pattern_response(url)
    if duplicate_response:
        return duplicate_response

    try:
        draft = scrape_pattern_from_url(url)
    except ScraperError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({"duplicate": False, "existing_pattern_id": None, "draft": draft}), 200


@patterns_bp.route("/preview-upload", methods=["POST"])
def preview_pattern_from_upload():
    """
    Like /preview, but the page's HTML comes from a file the user uploaded
    instead of being fetched by the server.

    This is the fallback for sites whose bot-detection (e.g. Cloudflare's
    JS challenge -- see scraper.ScraperError messages) blocks Yarnboard's
    automatic fetch entirely: the user opens the page in their own
    browser, saves it, and uploads the saved HTML here. `url` is still
    required and still used for dedup and attribution -- only the content
    used for extraction is user-supplied instead of fetched by us.

    multipart/form-data body: `url` (text field), `html_file` (file field).
    """
    user_id, error = _require_login()
    if error:
        return error

    url = (request.form.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400

    uploaded = request.files.get("html_file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "html_file is required"}), 400

    duplicate_response = _existing_pattern_response(url)
    if duplicate_response:
        return duplicate_response

    try:
        html = uploaded.read().decode("utf-8", errors="replace")
    except Exception:
        return jsonify({"error": "Could not read the uploaded file as text."}), 400

    try:
        draft = parse_pattern_html(html, url)
    except ScraperError as exc:
        return jsonify({"error": str(exc)}), 502

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
        return jsonify({"error": "original_url and title are required"}), 400

    if Pattern.query.filter_by(original_url=original_url).first():
        return jsonify({"error": "A pattern from this URL already exists."}), 409

    pattern = Pattern(
        original_url=original_url,
        title=title,
        author=(data.get("author") or None),
        source_site_name=data.get("source_site_name") or Pattern.derive_source_domain(original_url),
        source_domain=data.get("source_domain") or Pattern.derive_source_domain(original_url),
        materials=data.get("materials"),
        abbreviations=data.get("abbreviations"),
        instructions=data.get("instructions") or {},
        uploader_id=user_id,
    )
    db.session.add(pattern)
    try:
        db.session.commit()
    except IntegrityError:
        # Race: another request inserted the same original_url between our
        # check above and this commit. The unique constraint caught it.
        db.session.rollback()
        return jsonify({"error": "A pattern from this URL already exists."}), 409

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
    """
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_edit(user, pattern):
        return jsonify({"error": "You don't have permission to edit this pattern."}), 403

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    new_instructions = data.get("instructions") or {}
    instructions_changed = new_instructions != (pattern.instructions or {})

    pattern.title = title
    pattern.author = data.get("author") or None
    pattern.materials = data.get("materials")
    pattern.abbreviations = data.get("abbreviations")
    pattern.instructions = new_instructions
    if instructions_changed:
        pattern.instructions_version += 1

    db.session.commit()

    if instructions_changed:
        _notify_progress_users(pattern, editor_user_id=user_id)

    return jsonify({
        "message": "Pattern updated.",
        "pattern": pattern.to_dict(current_user_id=user_id),
    }), 200


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
            return jsonify({"error": "Pattern not found"}), 404
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
    """All published patterns, newest first. Public -- no login required."""
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
        return jsonify({"error": "part and index must reference a valid step"}), 400

    step_count = len(pattern.instructions[part])
    if not isinstance(index, int) or not (0 <= index < step_count):
        return jsonify({"error": "index out of range for this part"}), 400

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
