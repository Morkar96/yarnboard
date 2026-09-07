"""
Pattern endpoints: scrape-preview, submit, edit, publish/share (visibility),
the four list views (mine / saved / community / shared-with-me), pattern
detail, per-user checklist progress, and change notifications.

Endpoints that matter most for correctness:
  - POST /preview never writes to the database -- it's pure "show me what
    you'd get" so the user can review before publishing.
  - POST /submit is the only endpoint here that creates a Pattern row
    (stitch_fiddle/routes.py's import_link is the other one) -- always
    private (see Pattern.is_public's docstring in models.py), and it
    re-checks Pattern.find_duplicate right before inserting (in addition to
    the DB-level unique constraint on (original_url, uploader_id)) so two
    near-simultaneous submissions from the same uploader can't both
    succeed.
  - POST /<id>/publish is the only endpoint that makes a pattern
    community-visible; it's where a second public copy of the same URL
    gets rejected, since the DB constraint alone no longer enforces global
    uniqueness (see Pattern.find_duplicate).
  - GET /<id>, GET /community, PATCH /<id>/progress, and POST
    /saved all go through _can_view -- see its docstring for the
    visibility rule.
  - PATCH /<id> is the only endpoint that edits a pattern's content.
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
from ..email import send_pattern_shared_email, send_pattern_updated_email
from ..extensions import db
from ..models import Pattern, PatternShare, User, UserPatternProgress
from ..notifications import create_in_app_notification, is_enabled
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
    """Admins can edit any pattern; the uploader can edit their own; and
    anyone granted an edit-level PatternShare (see share_pattern's
    can_edit) can edit content but not manage sharing/publishing -- see
    the individual routes below for which ones additionally restrict to
    uploader-or-admin only."""
    if user.is_admin or pattern.uploader_id == user.id:
        return True
    share = PatternShare.query.filter_by(pattern_id=pattern.id, user_id=user.id).first()
    return bool(share and share.can_edit)


def _can_manage(user: User, pattern: Pattern) -> bool:
    """Publishing/unpublishing and managing who a pattern is shared with
    is uploader-or-admin only, even for a user with an edit-level share --
    those are ownership decisions, not content edits."""
    return user.is_admin or pattern.uploader_id == user.id


def _can_view(user: User | None, pattern: Pattern) -> bool:
    """Public patterns are visible to anyone, including a logged-out
    guest. A private one is visible only to its uploader, an admin, or a
    user explicitly granted access via PatternShare -- everyone else gets
    treated exactly like the pattern doesn't exist (see get_pattern's 404,
    not 403: a private pattern's existence isn't itself something to
    reveal to someone who can't see it)."""
    if pattern.is_public:
        return True
    if user is None:
        return False
    if user.is_admin or pattern.uploader_id == user.id:
        return True
    return PatternShare.query.filter_by(pattern_id=pattern.id, user_id=user.id).first() is not None


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


def _existing_pattern_response(url: str, uploader_id: int):
    """If `url` is already a duplicate for this uploader (see
    Pattern.find_duplicate), the short-circuit response for /preview and
    /preview-upload alike: duplicate=True plus its id, so the frontend can
    offer "view the existing pattern" instead of a review form for content
    that would just fail to save later. Returns None otherwise."""
    existing = Pattern.find_duplicate(url, uploader_id)
    if not existing:
        return None
    return jsonify({
        "duplicate": True,
        "existing_pattern_id": existing.id,
        "draft": None,
    }), 200


def _shared_pattern_id(url: str, user_id: int) -> int | None:
    """The id of a pattern already shared with this user for this exact
    URL, if any -- used to warn (not block) at preview time. Deliberately
    separate from find_duplicate/_existing_pattern_response: a pattern
    someone else shared with you isn't "yours" by find_duplicate's rule
    (so you're still entitled to submit your own copy), and a share can
    be revoked at any time, so this is informational only."""
    shared = (
        Pattern.query.join(PatternShare, PatternShare.pattern_id == Pattern.id)
        .filter(PatternShare.user_id == user_id, Pattern.original_url == url)
        .first()
    )
    return shared.id if shared else None


@patterns_bp.route("/preview", methods=["POST"])
def preview_pattern():
    """
    Scrape `url` and return a draft for the user to review -- no DB write.
    ---
    tags: [Patterns]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [url]
          properties:
            url: {type: string}
    responses:
      200:
        description: Either {duplicate:true, existing_pattern_id} or {duplicate:false, draft}
      400:
        description: url is required
      401:
        description: Not logged in
      502:
        description: The page couldn't be fetched/parsed (bot-detection, timeout, etc.)
    """
    user_id, error = _require_login()
    if error:
        return error

    url = (request.get_json(silent=True) or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required", "code": "url_required"}), 400

    duplicate_response = _existing_pattern_response(url, user_id)
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

    return jsonify({
        "duplicate": False,
        "existing_pattern_id": None,
        "already_shared_with_you": _shared_pattern_id(url, user_id),
        "draft": draft,
    }), 200


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
    ---
    tags: [Patterns]
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: url
        type: string
        required: true
      - in: formData
        name: html_file
        type: file
        required: true
        description: A saved HTML page or a PDF (sniffed by content, not filename)
    responses:
      200:
        description: Either {duplicate:true, existing_pattern_id} or {duplicate:false, draft}
      400:
        description: url or html_file missing
      401:
        description: Not logged in
      502:
        description: The file couldn't be parsed
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

    duplicate_response = _existing_pattern_response(url, user_id)
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

    return jsonify({
        "duplicate": False,
        "existing_pattern_id": None,
        "already_shared_with_you": _shared_pattern_id(url, user_id),
        "draft": draft,
    }), 200


@patterns_bp.route("/submit", methods=["POST"])
def submit_pattern():
    """
    Save a user-reviewed draft as a new, private Pattern row -- the
    uploader publishes it to the community explicitly, later, via POST
    /<id>/publish; submitting never does that itself.

    Expects the (possibly hand-edited) fields the /preview draft contained,
    plus original_url. This is the only place a Pattern row gets created.
    ---
    tags: [Patterns]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [original_url, title]
          properties:
            original_url: {type: string}
            title: {type: string}
            author: {type: string}
            materials: {type: string}
            abbreviations: {type: string}
            instructions: {type: object}
            photo_url: {type: string}
    responses:
      201:
        description: Pattern saved (private)
      400:
        description: original_url or title missing
      401:
        description: Not logged in
      409:
        description: A pattern from this URL already exists for this uploader (or is already public)
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

    if Pattern.find_duplicate(original_url, user_id):
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
        "message": "Pattern saved. It's private until you publish it to the community.",
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
    ---
    tags: [Patterns]
    parameters:
      - in: path
        name: pattern_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [title]
          properties:
            title: {type: string}
            author: {type: string}
            materials: {type: string}
            abbreviations: {type: string}
            instructions: {type: object}
            title_he: {type: string}
            materials_he: {type: string}
            abbreviations_he: {type: string}
            instructions_he: {type: object}
    responses:
      200:
        description: Pattern updated
      400:
        description: title missing, or instructions_he doesn't match instructions' structure
      401:
        description: Not logged in
      403:
        description: Not the uploader or an admin
      404:
        description: No such pattern
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
    # SQLAlchemy checks Python equality before deciding a column actually
    # changed, and dict equality ignores key order -- reordering parts
    # without touching their content would otherwise be silently dropped
    # from the UPDATE (the in-memory object looks right, but the DB row
    # never gets the new order). flag_modified forces it through
    # regardless of whether the content is equal, same as toggle_progress
    # below does for completed_steps.
    flag_modified(pattern, "instructions")
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


@patterns_bp.route("/<int:pattern_id>/publish", methods=["POST"])
def publish_pattern(pattern_id):
    """
    Make a private pattern community-visible. Reversible via
    POST /<id>/unpublish below. Same permission rule as managing sharing
    (_can_manage): the uploader or an admin, never anyone a pattern was
    merely shared with, even at edit level.

    No-ops if already public. Otherwise this is the one place a second
    public copy of the same URL gets rejected (see Pattern.find_duplicate
    -- the DB constraint alone only stops the *same* uploader from
    double-submitting, not two different uploaders each publishing their
    own private copy of the same source). Unpublishing frees the URL for
    someone else's already-submitted private copy to be published in turn
    -- see unpublish_pattern.
    """
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_manage(user, pattern):
        return jsonify({
            "error": "You don't have permission to publish this pattern.",
            "code": "edit_forbidden",
        }), 403

    if pattern.is_public:
        return jsonify({
            "message": "Already public.",
            "pattern": pattern.to_dict(current_user_id=user_id),
        }), 200

    conflict = Pattern.query.filter(
        Pattern.original_url == pattern.original_url,
        Pattern.is_public.is_(True),
        Pattern.id != pattern.id,
    ).first()
    if conflict:
        return jsonify({
            "error": "A pattern from this URL is already public.",
            "code": "pattern_already_exists",
            "existing_pattern_id": conflict.id,
        }), 409

    pattern.is_public = True
    db.session.commit()

    return jsonify({
        "message": "Pattern published to the community.",
        "pattern": pattern.to_dict(current_user_id=user_id),
    }), 200


@patterns_bp.route("/<int:pattern_id>/unpublish", methods=["POST"])
def unpublish_pattern(pattern_id):
    """
    Reverse a previous publish, making the pattern private again. Same
    permission rule as publish (_can_manage). No-ops if already private.

    Freeing this URL is implicit, not something this route has to do
    explicitly: publish's conflict check only ever looks at rows that are
    *currently* public (Pattern.is_public.is_(True)), so the moment this
    row's is_public flips False, it simply stops being the thing any
    future publish check finds -- another uploader's own already-
    submitted private copy of the same URL can now be published.
    """
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_manage(user, pattern):
        return jsonify({
            "error": "You don't have permission to unpublish this pattern.",
            "code": "edit_forbidden",
        }), 403

    if not pattern.is_public:
        return jsonify({
            "message": "Already private.",
            "pattern": pattern.to_dict(current_user_id=user_id),
        }), 200

    pattern.is_public = False
    db.session.commit()

    return jsonify({
        "message": "Pattern unpublished. It's private again.",
        "pattern": pattern.to_dict(current_user_id=user_id),
    }), 200


@patterns_bp.route("/<int:pattern_id>", methods=["DELETE"])
def delete_pattern(pattern_id):
    """
    Permanently delete a pattern -- uploader or an admin only
    (_can_manage), never an edit-level share. Cascades to its
    PatternShare grants and every UserPatternProgress row (including
    other users' progress, not just the deleter's), and drops it from
    everyone's saved list -- see Pattern.shares'/progress_entries'
    cascade="all, delete-orphan" in models.py. A StitchFiddleLink that
    previously imported this pattern has its imported_pattern_id merely
    nulled (nullable FK, no cascade) rather than being deleted itself, so
    the link remains and can be re-imported.
    """
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_manage(user, pattern):
        return jsonify({
            "error": "You don't have permission to delete this pattern.",
            "code": "edit_forbidden",
        }), 403

    db.session.delete(pattern)
    db.session.commit()

    return jsonify({"message": "Pattern deleted."}), 200


@patterns_bp.route("/<int:pattern_id>/shares", methods=["GET"])
def list_pattern_shares(pattern_id):
    """Everyone this pattern has been individually shared with. Same
    permission rule as editing -- only the uploader/an admin manages who
    else can see a private pattern.
    ---
    tags: [Patterns]
    parameters:
      - in: path
        name: pattern_id
        type: integer
        required: true
    responses:
      200:
        description: List of shares (id, user_id, username, created_at)
      401:
        description: Not logged in
      403:
        description: Not the uploader or an admin
      404:
        description: No such pattern
    """
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_manage(user, pattern):
        return jsonify({
            "error": "You don't have permission to manage this pattern's sharing.",
            "code": "edit_forbidden",
        }), 403

    shares = PatternShare.query.filter_by(pattern_id=pattern_id).all()
    return jsonify([s.to_dict() for s in shares]), 200


@patterns_bp.route("/<int:pattern_id>/shares", methods=["POST"])
def share_pattern(pattern_id):
    """Grant one specific user (by exact username) view access to a
    pattern that isn't public. Idempotent -- sharing with someone who
    already has access just returns the current list.
    ---
    tags: [Patterns]
    parameters:
      - in: path
        name: pattern_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [username]
          properties:
            username: {type: string}
    responses:
      201:
        description: Updated list of shares
      400:
        description: username missing, or is the pattern's own uploader
      401:
        description: Not logged in
      403:
        description: Not the uploader or an admin
      404:
        description: No such pattern, or no user with that username
    """
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_manage(user, pattern):
        return jsonify({
            "error": "You don't have permission to manage this pattern's sharing.",
            "code": "edit_forbidden",
        }), 403

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"error": "username is required", "code": "missing_fields"}), 400
    can_edit = bool(data.get("can_edit"))

    target = User.query.filter_by(username=username).first()
    if not target:
        # Raw message, not a fixed key -- names the specific username that
        # wasn't found, generated per-request like the scraper_error cases
        # elsewhere in this file.
        return jsonify({
            "error": f"No user found with username '{username}'.",
            "code": "share_user_not_found",
        }), 404
    if target.id == pattern.uploader_id:
        return jsonify({
            "error": "The uploader already has access to their own pattern.",
            "code": "cannot_share_with_uploader",
        }), 400

    if not PatternShare.query.filter_by(pattern_id=pattern_id, user_id=target.id).first():
        db.session.add(PatternShare(pattern_id=pattern_id, user_id=target.id, can_edit=can_edit))
        db.session.commit()

        create_in_app_notification(
            target, "pattern_shared",
            f"{user.username} shared \"{pattern.title}\" with you.",
            link=f"/pattern/{pattern.id}",
        )
        if is_enabled(target, "pattern_shared", "email"):
            try:
                send_pattern_shared_email(target.email, user.username, pattern)
            except Exception:
                current_app.logger.exception(
                    "Failed to send pattern-shared email to user %s for pattern %s",
                    target.id, pattern.id,
                )

    shares = PatternShare.query.filter_by(pattern_id=pattern_id).all()
    return jsonify([s.to_dict() for s in shares]), 201


@patterns_bp.route("/<int:pattern_id>/shares/<int:share_user_id>", methods=["PATCH"])
def update_pattern_share(pattern_id, share_user_id):
    """Change an existing share's permission level (view <-> edit) --
    the level isn't fixed at grant time, see PatternShare.can_edit's
    docstring. 404s if that user doesn't currently have a share (use
    POST .../shares to grant one in the first place)."""
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_manage(user, pattern):
        return jsonify({
            "error": "You don't have permission to manage this pattern's sharing.",
            "code": "edit_forbidden",
        }), 403

    share = PatternShare.query.filter_by(pattern_id=pattern_id, user_id=share_user_id).first()
    if not share:
        return jsonify({"error": "No share found for that user.", "code": "share_not_found"}), 404

    data = request.get_json(silent=True) or {}
    if "can_edit" not in data:
        return jsonify({"error": "can_edit is required", "code": "missing_fields"}), 400
    share.can_edit = bool(data.get("can_edit"))
    db.session.commit()

    shares = PatternShare.query.filter_by(pattern_id=pattern_id).all()
    return jsonify([s.to_dict() for s in shares]), 200


@patterns_bp.route("/<int:pattern_id>/shares/<int:share_user_id>", methods=["DELETE"])
def unshare_pattern(pattern_id, share_user_id):
    """Revoke a previously-granted share. A no-op (not an error) if that
    user never had access -- same "removing something that's already
    absent is fine" convention as unsave_pattern below.
    ---
    tags: [Patterns]
    parameters:
      - in: path
        name: pattern_id
        type: integer
        required: true
      - in: path
        name: share_user_id
        type: integer
        required: true
    responses:
      200:
        description: Access removed (or was already absent)
      401:
        description: Not logged in
      403:
        description: Not the uploader or an admin
      404:
        description: No such pattern
    """
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_manage(user, pattern):
        return jsonify({
            "error": "You don't have permission to manage this pattern's sharing.",
            "code": "edit_forbidden",
        }), 403

    PatternShare.query.filter_by(pattern_id=pattern_id, user_id=share_user_id).delete()
    db.session.commit()

    return jsonify({"message": "Access removed."}), 200


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

    Any logged-in user who can *view* this pattern can trigger this, not
    just its uploader -- translating doesn't change the pattern's
    authoritative English content, so it doesn't need the stricter
    _can_edit permission that editing/photo routes use. It does still
    need _can_view, though: without it, anyone could probe a private
    pattern's existence and burn a Gemini API call on content they can't
    otherwise see.
    ---
    tags: [Patterns]
    parameters:
      - in: path
        name: pattern_id
        type: integer
        required: true
    responses:
      200:
        description: Translated (or already had a translation) -- pattern returned either way
      401:
        description: Not logged in
      404:
        description: No such pattern, or not visible to this user
      502:
        description: Translation call failed
    """
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_view(user, pattern):
        return jsonify({"error": "Pattern not found.", "code": "pattern_not_found"}), 404

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
    ---
    tags: [Patterns]
    consumes:
      - multipart/form-data
    parameters:
      - in: path
        name: pattern_id
        type: integer
        required: true
      - in: formData
        name: photo
        type: file
        required: true
    responses:
      200:
        description: Photo updated
      400:
        description: photo missing, too large, or not a valid image
      401:
        description: Not logged in
      403:
        description: Not the uploader or an admin
      404:
        description: No such pattern
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
    ---
    tags: [Patterns]
    parameters:
      - in: path
        name: pattern_id
        type: integer
        required: true
    responses:
      200:
        description: Photo removed
      401:
        description: Not logged in
      403:
        description: Not the uploader or an admin
      404:
        description: No such pattern
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
    Stream a manually-uploaded photo's raw bytes. No login required for a
    *public* pattern -- same as its detail view (GET /<id>) -- but a
    private one gates on _can_view same as everywhere else, so a photo
    can't be fetched directly by URL to bypass the pattern's own
    visibility. Only ever the target of Pattern.to_dict()'s "photo_url"
    field when photo_data is actually set (a scraped photo_url points
    straight at the external source site instead, never through this
    route) -- so a 404 for a viewable pattern with no photo means the
    frontend is acting on stale data, not something to paper over by
    falling back to anything else.
    ---
    tags: [Patterns]
    produces:
      - image/jpeg
    parameters:
      - in: path
        name: pattern_id
        type: integer
        required: true
    responses:
      200:
        description: Raw image bytes
      404:
        description: No such pattern, not visible to this user, or it has no photo
    """
    user_id = get_current_user_id()
    pattern = Pattern.query.get_or_404(pattern_id)
    user = User.query.get(user_id) if user_id else None
    if not _can_view(user, pattern):
        return jsonify({"error": "Pattern not found.", "code": "pattern_not_found"}), 404
    if not pattern.photo_data:
        return jsonify({"error": "This pattern has no uploaded photo.", "code": "no_photo"}), 404

    return Response(pattern.photo_data, mimetype=pattern.photo_content_type or "image/jpeg")


def _notify_progress_users(pattern: Pattern, editor_user_id: int) -> None:
    """
    Notify (in-app and/or email, per each recipient's own
    notification_settings -- see notifications.py) everyone with
    meaningful checklist progress on `pattern` that it just changed.
    Called after instructions_version has already been bumped and
    committed. Best-effort per recipient -- one failed email send (bad
    address, Resend outage) is logged and skipped, never rolls back the
    edit or blocks the remaining recipients.
    """
    progress_rows = UserPatternProgress.query.filter_by(pattern_id=pattern.id).all()
    for progress in progress_rows:
        if progress.user_id == editor_user_id:
            continue  # no self-notification for your own edit
        if not progress.has_any_completed_step():
            continue  # stale-but-empty progress isn't real engagement

        recipient = progress.user
        create_in_app_notification(
            recipient, "pattern_updated",
            f"\"{pattern.title}\" has been updated -- your checklist progress on it was reset.",
            link=f"/pattern/{pattern.id}",
        )
        if not is_enabled(recipient, "pattern_updated", "email"):
            continue
        try:
            send_pattern_updated_email(recipient.email, pattern)
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
    ---
    tags: [Patterns]
    responses:
      200:
        description: List of {id, title} for stale patterns
      401:
        description: Not logged in
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
    ---
    tags: [Patterns]
    parameters:
      - in: path
        name: pattern_id
        type: integer
        required: true
    responses:
      200:
        description: Acknowledged (no-op if not actually stale)
      401:
        description: Not logged in
      404:
        description: No such pattern
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
    """Patterns this user personally uploaded.
    ---
    tags: [Patterns]
    responses:
      200:
        description: This user's uploaded patterns (public and private)
      401:
        description: Not logged in
    """
    user_id, error = _require_login()
    if error:
        return error

    patterns = Pattern.query.filter_by(uploader_id=user_id).order_by(Pattern.created_at.desc()).all()
    return jsonify([p.to_dict(current_user_id=user_id) for p in patterns]), 200


@patterns_bp.route("/saved", methods=["GET", "POST"])
def my_saved_patterns():
    """List this user's bookmarked community patterns, or bookmark a new one.
    ---
    tags: [Patterns]
    parameters:
      - in: body
        name: body
        required: false
        description: Only used for POST
        schema:
          type: object
          properties:
            pattern_id: {type: integer}
    responses:
      200:
        description: GET -- this user's saved patterns; POST -- confirmation message
      401:
        description: Not logged in
      404:
        description: (POST) No such pattern, or not visible to this user
    """
    user_id, error = _require_login()
    if error:
        return error
    user = User.query.get(user_id)

    if request.method == "POST":
        pattern_id = (request.get_json(silent=True) or {}).get("pattern_id")
        pattern = Pattern.query.get(pattern_id)
        if not pattern or not _can_view(user, pattern):
            return jsonify({"error": "Pattern not found", "code": "pattern_not_found"}), 404
        if pattern not in user.saved_patterns:
            user.saved_patterns.append(pattern)
            db.session.commit()
        return jsonify({"message": f"Pattern '{pattern.title}' saved."}), 200

    return jsonify([p.to_dict(current_user_id=user_id) for p in user.saved_patterns]), 200


@patterns_bp.route("/saved/<int:pattern_id>", methods=["DELETE"])
def unsave_pattern(pattern_id):
    """Remove a pattern from this user's saved/bookmarked list.
    ---
    tags: [Patterns]
    parameters:
      - in: path
        name: pattern_id
        type: integer
        required: true
    responses:
      200:
        description: Removed (no-op if it wasn't saved)
      401:
        description: Not logged in
    """
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
    """Published (is_public) patterns only, newest first. Public --
    unregistered visitors can browse the community library, same as a
    single pattern's detail view (get_pattern below); to_dict() already
    renders progress-free output when there's no logged-in user to look
    progress up for. Private and shared-but-not-public patterns never
    appear here regardless of viewer -- that's what /mine and
    /shared-with-me are for.
    ---
    tags: [Patterns]
    responses:
      200:
        description: All public patterns, newest first
    """
    user_id = get_current_user_id()

    patterns = (
        Pattern.query.filter_by(is_public=True).order_by(Pattern.created_at.desc()).all()
    )
    return jsonify([p.to_dict(current_user_id=user_id) for p in patterns]), 200


@patterns_bp.route("/shared-with-me", methods=["GET"])
def shared_with_me():
    """Patterns someone else explicitly shared with the current user (see
    PatternShare) -- distinct from /mine (your own uploads) and /saved
    (your bookmarks, which only ever contains patterns you could already
    see).
    ---
    tags: [Patterns]
    responses:
      200:
        description: Patterns explicitly shared with this user
      401:
        description: Not logged in
    """
    user_id, error = _require_login()
    if error:
        return error

    pattern_ids = [
        share.pattern_id for share in PatternShare.query.filter_by(user_id=user_id).all()
    ]
    patterns = (
        Pattern.query.filter(Pattern.id.in_(pattern_ids))
        .order_by(Pattern.created_at.desc())
        .all()
    )
    return jsonify([p.to_dict(current_user_id=user_id) for p in patterns]), 200


@patterns_bp.route("/<int:pattern_id>", methods=["GET"])
def get_pattern(pattern_id):
    """A single pattern's full detail, including this viewer's checklist
    progress if they're logged in. 404s (not 403) if this viewer can't
    see it (see _can_view) -- a private pattern's existence isn't itself
    revealed to someone without access.
    ---
    tags: [Patterns]
    parameters:
      - in: path
        name: pattern_id
        type: integer
        required: true
    responses:
      200:
        description: Full pattern detail
      404:
        description: No such pattern, or not visible to this viewer
    """
    user_id = get_current_user_id()
    pattern = Pattern.query.get_or_404(pattern_id)
    user = User.query.get(user_id) if user_id else None
    if not _can_view(user, pattern):
        return jsonify({"error": "Pattern not found.", "code": "pattern_not_found"}), 404
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
    ---
    tags: [Patterns]
    parameters:
      - in: path
        name: pattern_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [part, index, completed]
          properties:
            part: {type: string}
            index: {type: integer}
            completed: {type: boolean}
    responses:
      200:
        description: Progress updated
      400:
        description: That checklist step doesn't exist
      401:
        description: Not logged in
      404:
        description: No such pattern, or not visible to this user
    """
    user_id, error = _require_login()
    if error:
        return error

    user = User.query.get(user_id)
    pattern = Pattern.query.get_or_404(pattern_id)
    if not _can_view(user, pattern):
        return jsonify({"error": "Pattern not found.", "code": "pattern_not_found"}), 404

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
