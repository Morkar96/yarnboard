"""
Database models for Yarnboard.

Three tables:
  - User: an account. Tracks patterns it uploaded (one-to-many) and patterns
    it bookmarked from the community (many-to-many, via saved_patterns).
  - Pattern: a single knitting/crochet pattern, scraped from a source URL.
    Patterns are shared/public once submitted -- every user sees the same
    row -- and are deduplicated on `original_url`.
  - UserPatternProgress: which checklist steps a *specific* user has ticked
    off on a *specific* pattern. This is intentionally its own table rather
    than a field on Pattern -- see its docstring below for why.
"""

from urllib.parse import urlparse

from .extensions import db

# Association table for the many-to-many "saved / bookmarked" relationship
# between users and patterns they didn't necessarily upload themselves.
saved_patterns = db.Table(
    "saved_patterns",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("pattern_id", db.Integer, db.ForeignKey("pattern.id"), primary_key=True),
)


class User(db.Model):
    """A Yarnboard account."""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    # Can edit ANY pattern, not just their own uploads. Set via the
    # `flask make-admin <email>` CLI command (see app/__init__.py) --
    # deliberately not a hardcoded email comparison in route logic.
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    # Login is blocked until this is true (see auth/routes.py's login()).
    # email_verify_token is the single-use secret mailed in the
    # verification link; it and its timestamp are cleared once consumed
    # (or replaced wholesale by /api/resend-verification). The Python-side
    # default=False only governs ORM inserts -- the add-email-verification-
    # columns migration in app/__init__.py deliberately backfills existing
    # rows as *verified*, so this only gates newly-registered accounts.
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    email_verify_token = db.Column(db.String(64), unique=True, nullable=True)
    email_verify_token_created_at = db.Column(db.DateTime, nullable=True)

    # Patterns this user personally submitted (shown on "My Uploads").
    uploaded_patterns = db.relationship("Pattern", backref="uploader", lazy=True)

    # Patterns this user bookmarked from the community (shown on "My Saved").
    # This is independent of who uploaded the pattern.
    saved_patterns = db.relationship(
        "Pattern",
        secondary=saved_patterns,
        lazy="subquery",
        backref=db.backref("saved_by", lazy=True),
    )

    def __repr__(self):
        return f"<User {self.username}>"


class Pattern(db.Model):
    """
    A single pattern, scraped (with human review) from a source webpage.

    `instructions` is stored as JSON shaped like:
        {"Part 1: Cast On": ["Cast on 50 stitches.", "Join in the round."],
         "Part 2: Body": ["Knit 20 rounds.", "Purl 1 round."]}
    i.e. an ordered mapping of part name -> ordered list of step strings.
    Deliberately no "completed" flag lives here: this row is shared by every
    user who views/saves the pattern, so per-user checklist state is tracked
    separately in UserPatternProgress and merged in at read time by
    to_dict(current_user_id=...).
    """

    id = db.Column(db.Integer, primary_key=True)
    original_url = db.Column(db.String(512), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)

    # Attribution to the *original* creator/site, as distinct from the
    # Yarnboard user who uploaded it (see `uploader` backref below).
    author = db.Column(db.String(100), nullable=True)
    source_site_name = db.Column(db.String(200), nullable=True)
    source_domain = db.Column(db.String(200), nullable=True)

    materials = db.Column(db.Text, nullable=True)
    abbreviations = db.Column(db.Text, nullable=True)
    instructions = db.Column(db.JSON, nullable=True)
    # Bumped only when `instructions` actually changes via an edit (see
    # patterns/routes.py's edit endpoint) -- this is the whole basis for
    # detecting stale per-user progress. See UserPatternProgress below for
    # how it's consumed; deliberately NOT used for edit-conflict detection
    # (last-write-wins on edits, same as every other write path here).
    instructions_version = db.Column(db.Integer, nullable=False, default=1)

    # Photo of the finished/made object. `photo_url` is a passthrough
    # external URL found while scraping (never downloaded/hosted by us);
    # `photo_data`/`photo_content_type` is an image whose bytes live
    # directly in this row (see backend/app/photo.py for the resize/
    # re-encode step) -- Render's web service has no persistent disk, so
    # this is the storage mechanism, not a stopgap. `photo_source` records
    # which one is authoritative so to_dict() doesn't have to guess from
    # nullability alone: "scraped" (photo_url) or "uploaded" (a user's own
    # photo of their finished object, via patterns/routes.py's photo
    # upload endpoint). An upload always replaces whatever photo was
    # there before.
    photo_source = db.Column(db.String(20), nullable=True)
    photo_url = db.Column(db.String(1000), nullable=True)
    photo_data = db.Column(db.LargeBinary, nullable=True)
    photo_content_type = db.Column(db.String(50), nullable=True)

    # A Stitch Fiddle chart's grid, imported via stitch_fiddle/routes.py
    # (see backend/app/stitchfiddle.py for the fetch/decode mechanics).
    # Deliberately separate from the photo_* columns above -- unlike a
    # photo, this is structured data (one palette-index byte per cell,
    # row-major) meant to be rendered as an actual colored <table> on the
    # frontend (PatternChartGrid.tsx), not a flattened image.
    # chart_palette is a list of {"hex": "#849c62", "label": "Color 1"} in
    # the same index order the grid bytes reference.
    chart_grid_data = db.Column(db.LargeBinary, nullable=True)
    chart_grid_columns = db.Column(db.Integer, nullable=True)
    chart_grid_rows = db.Column(db.Integer, nullable=True)
    chart_palette = db.Column(db.JSON, nullable=True)

    # Hebrew translation, populated on-demand via POST /<id>/translate (see
    # patterns/routes.py) rather than at submit time -- a pattern nobody
    # ever views in Hebrew never costs a translation API call.
    #
    # instructions_he is keyed by the *exact same keys* as `instructions`
    # (English part names) -- never translated keys of its own. Each value
    # is {"heading_he": str, "steps_he": [str, ...]}, with steps_he the
    # same length as the corresponding English steps list. This is
    # deliberate: UserPatternProgress.completed_steps and toggle_progress
    # (see below, and patterns/routes.py) key checklist progress by the
    # English part name string, so a Hebrew-mode checklist looks up
    # instructions_he[part] purely for display text while still reporting
    # progress against the same English `part`/index the English view
    # would use. If instructions_he ever had its own translated keys,
    # Hebrew-mode progress would have nothing compatible to attach to.
    # The edit endpoint enforces this shape (same keys, same list lengths)
    # rather than trusting it.
    title_he = db.Column(db.String(200), nullable=True)
    materials_he = db.Column(db.Text, nullable=True)
    abbreviations_he = db.Column(db.Text, nullable=True)
    instructions_he = db.Column(db.JSON, nullable=True)
    # False until a human (uploader or admin) has confirmed the
    # auto-translation -- see _validate_instructions_he in
    # patterns/routes.py's edit_pattern, which is what flips this True.
    translation_reviewed = db.Column(db.Boolean, nullable=False, default=False)

    uploader_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    @staticmethod
    def derive_source_domain(url: str) -> str:
        """Bare-domain fallback (e.g. 'ravelry.com') used when a page has no
        og:site_name meta tag. Shared by the scraper and by callers that
        need to recompute it without re-scraping."""
        netloc = urlparse(url).netloc
        return netloc[4:] if netloc.startswith("www.") else netloc

    def to_dict(self, current_user_id=None):
        """
        Serialize this pattern for the API.

        If `current_user_id` is given, this user's UserPatternProgress row
        (if any) is merged in so each step in `instructions` is returned as
        {"step": <text>, "completed": <bool>} instead of a bare string --
        convenient for the frontend checklist. Without a user id (public/
        anonymous views), steps are returned as {"step": <text>,
        "completed": False} so the response shape is always the same.

        If the pattern has been edited since this user's progress was last
        touched (progress.pattern_version < self.instructions_version), it's
        stale: rendered as all-unchecked here, same as having no progress at
        all. This method never writes to the DB -- the actual cleanup of a
        stale row happens lazily elsewhere (toggle_progress) or explicitly
        (the /acknowledge-update endpoint), never as a side effect of a read.
        """
        instructions_with_progress = {}
        progress = None
        if current_user_id is not None:
            progress = UserPatternProgress.query.filter_by(
                user_id=current_user_id, pattern_id=self.id
            ).first()

        stale = progress is not None and progress.pattern_version < self.instructions_version

        for part, steps in (self.instructions or {}).items():
            completed_flags = None
            if progress and not stale and part in (progress.completed_steps or {}):
                completed_flags = progress.completed_steps[part]

            instructions_with_progress[part] = [
                {
                    "step": step_text,
                    "completed": bool(completed_flags[i])
                    if completed_flags and i < len(completed_flags)
                    else False,
                }
                for i, step_text in enumerate(steps)
            ]

        return {
            "id": self.id,
            "original_url": self.original_url,
            "title": self.title,
            "author": self.author,
            "source_site_name": self.source_site_name,
            "source_domain": self.source_domain,
            "materials": self.materials,
            "abbreviations": self.abbreviations,
            "instructions": instructions_with_progress,
            # A single opaque URL regardless of source: an uploaded photo is
            # served from our own streaming route (see GET /<id>/photo in
            # patterns/routes.py); a scraped photo is the external URL
            # directly -- no proxying/downloading needed for that case.
            "photo_url": (
                f"/api/patterns/{self.id}/photo" if self.photo_data
                else self.photo_url if self.photo_url
                else None
            ),
            "has_photo": bool(self.photo_data or self.photo_url),
            "chart_grid": {
                "column_count": self.chart_grid_columns,
                "row_count": self.chart_grid_rows,
                "palette": self.chart_palette,
                "cells": list(self.chart_grid_data),
            } if self.chart_grid_data else None,
            "translations": {
                "he": {
                    "title": self.title_he,
                    "materials": self.materials_he,
                    "abbreviations": self.abbreviations_he,
                    "instructions": self.instructions_he,
                    "reviewed": self.translation_reviewed,
                } if self.title_he else None,
            },
            "uploader": self.uploader.username if self.uploader else "Unknown",
            "uploader_id": self.uploader_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserPatternProgress(db.Model):
    """
    One user's checklist progress on one pattern.

    `completed_steps` mirrors the shape of Pattern.instructions but with
    booleans instead of step text, e.g.:
        {"Part 1: Cast On": [true, false], "Part 2: Body": [false, false]}
    Steps are matched *by index*, not by re-storing the step text, so this
    row assumes Pattern.instructions doesn't change shape relative to
    whatever `pattern_version` this row is stamped with.

    Patterns CAN change now (see the edit endpoint in patterns/routes.py),
    which is exactly what `pattern_version` guards against: it's set to
    `Pattern.instructions_version` whenever this row is created or wiped,
    and compared against the pattern's current version everywhere progress
    is read or written (Pattern.to_dict, toggle_progress, the notifications
    endpoint, /acknowledge-update). A row whose `pattern_version` is behind
    the pattern's is stale and must never be trusted at face value -- see
    those call sites for the three different (read-only vs. write) rules
    that apply.
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    pattern_id = db.Column(db.Integer, db.ForeignKey("pattern.id"), nullable=False)
    completed_steps = db.Column(db.JSON, nullable=False, default=dict)
    pattern_version = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    user = db.relationship("User", backref=db.backref("progress_entries", lazy=True))
    pattern = db.relationship("Pattern", backref=db.backref("progress_entries", lazy=True))

    __table_args__ = (
        db.UniqueConstraint("user_id", "pattern_id", name="uq_user_pattern_progress"),
    )

    def has_any_completed_step(self) -> bool:
        """True if at least one step is actually checked off. Used to keep
        the update-notification banner and email from firing for a progress
        row that's technically stale but represents no real engagement
        (e.g. a saved-but-never-opened pattern)."""
        return any(any(flags) for flags in (self.completed_steps or {}).values())


class StitchFiddleLink(db.Model):
    """
    A Stitch Fiddle (stitchfiddle.com) chart share link a user has saved,
    so Yarnboard can turn it into a real Pattern on demand -- see
    backend/app/stitchfiddle.py for the fetch/decode mechanics and
    stitch_fiddle/routes.py for the import flow.

    This is private per-user data (closer to UserPatternProgress than to
    the public, shared Pattern table): only the owning user can see, check,
    or remove their own saved links. `imported_pattern_id` is null until
    the user clicks Import; once set, re-importing is a no-op (see the
    import route) rather than refreshing the Pattern, since the user may
    have hand-edited the pattern's title/materials/instructions since.
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    share_url = db.Column(db.String(512), nullable=False)
    chart_id = db.Column(db.String(80), nullable=False)
    imported_pattern_id = db.Column(db.Integer, db.ForeignKey("pattern.id"), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship("User", backref=db.backref("stitch_fiddle_links", lazy=True))
    imported_pattern = db.relationship("Pattern")

    __table_args__ = (
        # Keyed on chart_id, not share_url string equality -- the same
        # chart is reachable via multiple URL variants (locale-prefixed,
        # trailing slash), but chart_id (parsed by
        # stitchfiddle.parse_share_url) is its actual stable identity.
        db.UniqueConstraint("user_id", "chart_id", name="uq_user_chart_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "share_url": self.share_url,
            "chart_id": self.chart_id,
            "imported_pattern_id": self.imported_pattern_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
