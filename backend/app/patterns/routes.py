"""
Pattern endpoints: scrape-preview, submit/publish, the three list views
(mine / saved / community), pattern detail, and per-user checklist
progress.

Two endpoints matter most for correctness:
  - POST /preview never writes to the database -- it's pure "show me what
    you'd get" so the user can review before publishing.
  - POST /submit is the only endpoint that creates a Pattern row, and it
    re-checks the URL uniqueness right before inserting (in addition to the
    DB-level unique constraint) so two near-simultaneous submissions of the
    same URL can't both succeed.
"""

from flask import Blueprint, request, jsonify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from ..extensions import db
from ..models import Pattern, User, UserPatternProgress
from ..scraper import scrape_pattern_from_url, ScraperError
from ..utils import get_current_user_id

patterns_bp = Blueprint("patterns", __name__, url_prefix="/api/patterns")


def _require_login():
    """Return (user_id, None) or (None, error_response) for route guards."""
    user_id = get_current_user_id()
    if not user_id:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    return user_id, None


@patterns_bp.route("/preview", methods=["POST"])
def preview_pattern():
    """
    Scrape `url` and return a draft for the user to review -- no DB write.

    If a Pattern with this original_url already exists, short-circuits with
    duplicate=True and the existing pattern's id so the frontend can offer
    "view the existing pattern" instead of showing a review form for
    content that would just fail to save later.
    """
    user_id, error = _require_login()
    if error:
        return error

    url = (request.get_json(silent=True) or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400

    existing = Pattern.query.filter_by(original_url=url).first()
    if existing:
        return jsonify({
            "duplicate": True,
            "existing_pattern_id": existing.id,
            "draft": None,
        }), 200

    try:
        draft = scrape_pattern_from_url(url)
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
        progress = UserPatternProgress(user_id=user_id, pattern_id=pattern_id, completed_steps={})
        db.session.add(progress)

    flags = progress.completed_steps.get(part) or [False] * step_count
    # Pad defensively in case the part's step count differs from what's
    # already recorded (shouldn't happen since patterns are immutable, but
    # cheap to guard against an out-of-sync progress row).
    if len(flags) < step_count:
        flags = flags + [False] * (step_count - len(flags))
    flags[index] = completed

    progress.completed_steps[part] = flags
    flag_modified(progress, "completed_steps")
    db.session.commit()

    return jsonify({"completed_steps": progress.completed_steps}), 200
