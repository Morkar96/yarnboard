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
