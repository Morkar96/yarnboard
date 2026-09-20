"""
Stitch Fiddle chart-import endpoints: save/list/remove a share link, and
turn one into a real Pattern on demand ("Import").

Deliberately separate from patterns/routes.py: a StitchFiddleLink is
private per-user data (only its owner can see or act on it) regardless of
what happens to the Pattern it eventually becomes -- which itself starts
private too (see Pattern.is_public's docstring in models.py) and stays
that way until its uploader explicitly publishes it. See
backend/app/stitchfiddle.py for the actual fetch/decode mechanics -- this
file is orchestration only.
"""

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from .. import stitchfiddle
from ..extensions import db
from ..models import Pattern, StitchFiddleLink
from ..stitchfiddle import StitchFiddleError
from ..utils import get_current_user_id

stitch_fiddle_bp = Blueprint("stitch_fiddle", __name__, url_prefix="/api/stitch-fiddle")


def _require_login():
    """Return (user_id, None) or (None, error_response) for route guards."""
    user_id = get_current_user_id()
    if not user_id:
        return None, (jsonify({"error": "Unauthorized", "code": "unauthorized"}), 401)
    return user_id, None


@stitch_fiddle_bp.route("/links", methods=["GET"])
def list_links():
    """This user's own saved Stitch Fiddle links -- never anyone else's,
    there's no community-wide variant of this list.
    ---
    tags: [StitchFiddle]
    responses:
      200:
        description: This user's saved links
      401:
        description: Not logged in
    """
    user_id, error = _require_login()
    if error:
        return error

    links = (
        StitchFiddleLink.query.filter_by(user_id=user_id)
        .order_by(StitchFiddleLink.created_at.desc())
        .all()
    )
    return jsonify([link.to_dict() for link in links]), 200


@stitch_fiddle_bp.route("/links", methods=["POST"])
def save_link():
    """
    Save a new Stitch Fiddle share link. Only validates the URL shape and
    extracts its chart_id -- doesn't fetch the chart itself (that's what
    Import does), so saving a link stays cheap and doesn't require the
    chart to be public yet.

    If this user already saved this chart_id, returns the existing row
    rather than erroring -- pasting the same link twice is a no-op, not a
    mistake worth surfacing as an error.
    ---
    tags: [StitchFiddle]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [share_url]
          properties:
            share_url: {type: string}
    responses:
      200:
        description: This user already saved this chart_id -- existing row returned
      201:
        description: Link saved
      400:
        description: Not a valid Stitch Fiddle share URL
      401:
        description: Not logged in
    """
    user_id, error = _require_login()
    if error:
        return error

    share_url = (request.get_json(silent=True) or {}).get("share_url", "").strip()
    try:
        chart_id = stitchfiddle.parse_share_url(share_url)
    except StitchFiddleError as exc:
        # Raw message, not a fixed key -- varies per failure (bad URL
        # shape, unrecognized domain, etc.), same reasoning as
        # patterns/routes.py's scraper_error cases.
        return jsonify({"error": str(exc), "code": "invalid_share_url"}), 400

    existing = StitchFiddleLink.query.filter_by(user_id=user_id, chart_id=chart_id).first()
    if existing:
        return jsonify(existing.to_dict()), 200

    link = StitchFiddleLink(user_id=user_id, share_url=share_url, chart_id=chart_id)
    db.session.add(link)
    db.session.commit()

    return jsonify(link.to_dict()), 201


@stitch_fiddle_bp.route("/links/<int:link_id>", methods=["DELETE"])
def delete_link(link_id):
    """
    Remove one of this user's saved Stitch Fiddle links.
    ---
    tags: [StitchFiddle]
    parameters:
      - in: path
        name: link_id
        type: integer
        required: true
    responses:
      200:
        description: Link removed
      401:
        description: Not logged in
      403:
        description: Not this user's link
      404:
        description: No such link
    """
    user_id, error = _require_login()
    if error:
        return error

    link = StitchFiddleLink.query.get_or_404(link_id)
    if link.user_id != user_id:
        return jsonify({
            "error": "You don't have permission to remove this link.",
            "code": "link_forbidden",
        }), 403

    db.session.delete(link)
    db.session.commit()
    return jsonify({"message": "Link removed."}), 200


@stitch_fiddle_bp.route("/links/<int:link_id>/import", methods=["POST"])
def import_link(link_id):
    """
    Turn a saved link into a real Pattern.

    Re-importing an already-imported link is a no-op (returns the
    existing Pattern) rather than refreshing it -- the user may have
    hand-edited the pattern's title/materials/instructions since, and
    silently overwriting that would be surprising. Deliberately no
    "review before publishing" step here, unlike scraper.py's HTML
    extraction: everything pulled from Stitch Fiddle (title, palette,
    grid) is exact structured data, not a heuristic guess, so there's
    nothing for a human to correct first -- the user can still edit the
    resulting pattern normally afterward.
    ---
    tags: [StitchFiddle]
    parameters:
      - in: path
        name: link_id
        type: integer
        required: true
    responses:
      200:
        description: Already imported (or a duplicate of an existing Pattern) -- that Pattern returned
      201:
        description: Chart imported into a new private Pattern
      401:
        description: Not logged in
      403:
        description: Not this user's link
      404:
        description: No such link
      502:
        description: Stitch Fiddle fetch failed (timeout, chart no longer public, etc.)
    """
    user_id, error = _require_login()
    if error:
        return error

    link = StitchFiddleLink.query.get_or_404(link_id)
    if link.user_id != user_id:
        return jsonify({
            "error": "You don't have permission to import this link.",
            "code": "link_forbidden",
        }), 403

    if link.imported_pattern_id:
        pattern = Pattern.query.get(link.imported_pattern_id)
        return jsonify({
            "message": "Already imported.",
            "pattern": pattern.to_dict(current_user_id=user_id),
        }), 200

    try:
        chart = stitchfiddle.fetch_chart(link.share_url)
        grid_bytes = stitchfiddle.decode_grid(
            chart["grid_rows_field"], chart["column_count"], chart["row_count"]
        )
        palette = stitchfiddle.palette_to_json(chart["palette"])
    except StitchFiddleError as exc:
        # Raw message, not a fixed key -- see save_link's identical case
        # above for why (varies per failure: fetch timeout, access
        # denied, chart no longer public, etc.).
        return jsonify({"error": str(exc), "code": "stitchfiddle_fetch_error"}), 502

    # Someone (possibly this same user, via a normal manual submit) may
    # already have a Pattern for this exact URL -- link to it instead of
    # creating a duplicate, same dedup-by-original_url philosophy as the
    # rest of this app's Pattern table. find_duplicate only matches a
    # published pattern (any uploader) or this same uploader's own
    # (possibly still-private) copy -- someone else's private pattern for
    # this URL doesn't count, they're entitled to their own private import.
    existing = Pattern.find_duplicate(link.share_url, user_id)
    if existing:
        link.imported_pattern_id = existing.id
        db.session.commit()
        return jsonify({
            "message": "This chart was already published to the community."
            if existing.is_public else "You already imported this chart.",
            "pattern": existing.to_dict(current_user_id=user_id),
        }), 200

    pattern = Pattern(
        original_url=link.share_url,
        title=chart["title"] or "Untitled Stitch Fiddle Chart",
        source_site_name="Stitch Fiddle",
        source_domain="stitchfiddle.com",
        materials=stitchfiddle.materials_text_from_palette(chart["palette"]),
        instructions={},
        chart_grid_data=grid_bytes,
        chart_grid_columns=chart["column_count"],
        chart_grid_rows=chart["row_count"],
        chart_palette=palette,
        uploader_id=user_id,
    )
    db.session.add(pattern)
    try:
        db.session.commit()
    except IntegrityError:
        # Race: another of this user's own tabs/requests imported or
        # submitted this same URL between our check above and this commit
        # -- the (original_url, uploader_id) constraint is what caught it,
        # so that's the row to link to instead of failing.
        db.session.rollback()
        pattern = Pattern.query.filter_by(original_url=link.share_url, uploader_id=user_id).first()

    link.imported_pattern_id = pattern.id
    db.session.commit()

    return jsonify({
        "message": "Chart imported.",
        "pattern": pattern.to_dict(current_user_id=user_id),
    }), 201
