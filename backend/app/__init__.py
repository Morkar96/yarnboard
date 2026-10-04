"""
Application factory.

create_app() builds and configures the Flask app: loads config, wires up
the shared extensions (db, bcrypt), enables CORS (still needed locally,
where the Vite dev server and Flask run as separate processes on
different ports), registers the two blueprints that hold all the actual
API routes, and serves the built React frontend directly -- this is a
single combined Render service, not separate frontend/backend services,
so Flask is responsible for handing back the SPA's static files too (see
serve_frontend below). Keeping route logic out of this file (in
auth/routes.py and patterns/routes.py) is what the "auth" vs "patterns"
split buys us: each blueprint is a self-contained module you can read
top-to-bottom for one concern, without wading through the other.
"""

from pathlib import Path
from flasgger import Swagger

import click
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from .config import INSECURE_DEFAULT_SECRET_KEY, ProdConfig, get_config
from .extensions import db, bcrypt, limiter

# backend/app/__init__.py -> up three levels is the repo root, then into
# the frontend's Vite build output. Doesn't exist until `npm run build`
# has been run (see serve_frontend's 404 fallback for local dev, where the
# Vite dev server is used instead and this path is never populated).
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def create_app(config_overrides: dict | None = None):
    """
    `config_overrides`, if given, is applied to `app.config` before
    `db.init_app(app)` runs -- required for tests/conftest.py to point at
    an isolated database. Flask-SQLAlchemy 3.x builds the engine eagerly
    inside `init_app()`, reading `SQLALCHEMY_DATABASE_URI` at that exact
    moment; updating `app.config` afterward (the old approach here) is a
    no-op against the engine that's already cached, since it's not
    re-read lazily on each query the way it was in Flask-SQLAlchemy 2.x.
    Concretely, that bug meant every pytest run's `db.create_all()`/
    `drop_all()` was silently operating on the real local
    `backend/instance/yarnboard.db` instead of a test's temp file --
    creating tables, then dropping them all at teardown.
    """
    app = Flask(__name__)
    config_class = get_config()
    app.config.from_object(config_class)
    if config_overrides:
        app.config.update(config_overrides)
    # Flask's JSON provider alphabetizes dict keys by default, recursively
    # -- Pattern.instructions is an ordered {part_name: [steps]} dict whose
    # key order is meaningful (see PatternReviewForm.tsx's movePart, which
    # lets an uploader deliberately reorder parts), so a plain jsonify()
    # would silently re-sort it back to alphabetical on every response,
    # discarding that order.
    app.json.sort_keys = False

    # A forgotten SECRET_KEY env var in production would otherwise fall
    # back to a hardcoded, publicly-known string -- since Flask's session
    # cookie is signed with this key and stores nothing but {"user_id": N},
    # that would let anyone forge a cookie and impersonate any user
    # (including admins). Fail loudly at startup instead of silently
    # running insecurely; config_overrides (used by tests) is exempt since
    # it deliberately sets its own throwaway SECRET_KEY.
    if (
        config_class is ProdConfig
        and not (config_overrides or {}).get("SECRET_KEY")
        and app.config["SECRET_KEY"] == INSECURE_DEFAULT_SECRET_KEY
    ):
        raise RuntimeError(
            "SECRET_KEY environment variable is not set. Refusing to start in "
            "production with the insecure default secret key -- set a real "
            "random value (see render.yaml)."
        )
    # Initialize Swagger with default configurations
    swagger = Swagger(app)

    db.init_app(app)
    bcrypt.init_app(app)
    limiter.init_app(app)

    # supports_credentials=True is required because the frontend sends the
    # session cookie on every request (credentials: 'include'); the origins
    # allowlist comes from CORS_ORIGINS so prod only trusts the deployed
    # frontend URL, not "*".
    CORS(app, supports_credentials=True, origins=app.config["CORS_ORIGINS"])

    from .auth.routes import auth_bp
    from .patterns.routes import patterns_bp
    from .stitch_fiddle.routes import stitch_fiddle_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(patterns_bp)
    app.register_blueprint(stitch_fiddle_bp)

    @app.cli.command("init-db")
    def init_db():
        """`flask --app wsgi init-db` -- create all tables. Safe to re-run;
        only creates tables that don't already exist. This is the one-off
        substitute for a migration tool, appropriate for this app's size
        (see README for the tradeoff)."""
        with app.app_context():
            db.create_all()
        print("Database tables created.")

    @app.cli.command("add-versioning-columns")
    def add_versioning_columns():
        """`flask --app wsgi add-versioning-columns` -- one-off, idempotent
        ALTER TABLE for the pattern-editing feature's new columns
        (User.is_admin, Pattern.instructions_version,
        UserPatternProgress.pattern_version). `init-db`'s db.create_all()
        only creates missing tables, never adds columns to tables that
        already exist -- for a database created before this feature (e.g.
        the live Neon database), this command is what actually adds them.
        Safe to re-run (IF NOT EXISTS). Not needed for a brand-new
        database -- init-db already creates the columns for you there.
        Local SQLite dev: simpler to just delete yarnboard.db and re-run
        init-db instead of using this."""
        with app.app_context():
            db.session.execute(db.text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS instructions_version INTEGER NOT NULL DEFAULT 1'
            ))
            db.session.execute(db.text(
                'ALTER TABLE user_pattern_progress ADD COLUMN IF NOT EXISTS pattern_version INTEGER NOT NULL DEFAULT 1'
            ))
            db.session.commit()
        print("Versioning columns added.")

    @app.cli.command("add-photo-columns")
    def add_photo_columns():
        """`flask --app wsgi add-photo-columns` -- one-off, idempotent
        ALTER TABLE for the pattern-photo feature's new columns
        (Pattern.photo_source, photo_url, photo_data, photo_content_type).
        Same rationale as add-versioning-columns above: db.create_all()
        only creates missing tables, never adds columns to a table that
        already exists, so this is what actually adds them to the live
        Neon database. Safe to re-run (IF NOT EXISTS). Not needed for a
        brand-new database -- init-db already creates the columns there."""
        with app.app_context():
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS photo_source VARCHAR(20)'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS photo_url VARCHAR(1000)'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS photo_data BYTEA'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS photo_content_type VARCHAR(50)'
            ))
            db.session.commit()
        print("Photo columns added.")

    @app.cli.command("add-chart-grid-columns")
    def add_chart_grid_columns():
        """`flask --app wsgi add-chart-grid-columns` -- one-off, idempotent
        ALTER TABLE for the Stitch Fiddle chart-import feature's new
        columns (Pattern.chart_grid_data, chart_grid_columns,
        chart_grid_rows, chart_palette). Same rationale as
        add-photo-columns above: db.create_all() only creates missing
        tables, never adds columns to a table that already exists, so
        this is what actually adds them to the live Neon database. Safe
        to re-run (IF NOT EXISTS). Not needed for a brand-new database --
        init-db already creates the columns there."""
        with app.app_context():
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS chart_grid_data BYTEA'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS chart_grid_columns INTEGER'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS chart_grid_rows INTEGER'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS chart_palette JSON'
            ))
            db.session.commit()
        print("Chart grid columns added.")

    @app.cli.command("add-hebrew-translation-columns")
    def add_hebrew_translation_columns():
        """`flask --app wsgi add-hebrew-translation-columns` -- one-off,
        idempotent ALTER TABLE for the Hebrew-translation feature's new
        columns (Pattern.title_he, materials_he, abbreviations_he,
        instructions_he, translation_reviewed). Same rationale as
        add-chart-grid-columns above. Safe to re-run (IF NOT EXISTS). Not
        needed for a brand-new database -- init-db already creates the
        columns there."""
        with app.app_context():
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS title_he VARCHAR(200)'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS materials_he TEXT'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS abbreviations_he TEXT'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS instructions_he JSON'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS translation_reviewed '
                "BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            db.session.commit()
        print("Hebrew translation columns added.")

    @app.cli.command("add-english-translation-columns")
    def add_english_translation_columns():
        """`flask --app wsgi add-english-translation-columns` -- one-off,
        idempotent ALTER TABLE for the reverse-direction (Hebrew-primary
        pattern -> English overlay) translation columns (Pattern.
        title_en, materials_en, abbreviations_en, instructions_en,
        translation_en_reviewed). Exact mirror of
        add-hebrew-translation-columns above. Safe to re-run (IF NOT
        EXISTS). Not needed for a brand-new database -- init-db already
        creates the columns there."""
        with app.app_context():
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS title_en VARCHAR(200)'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS materials_en TEXT'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS abbreviations_en TEXT'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS instructions_en JSON'
            ))
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS translation_en_reviewed '
                "BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            db.session.commit()
        print("English translation columns added.")

    @app.cli.command("add-email-verification-columns")
    def add_email_verification_columns():
        """`flask --app wsgi add-email-verification-columns` -- one-off,
        idempotent ALTER TABLE for the email-verification feature's new
        columns (User.email_verified, email_verify_token,
        email_verify_token_created_at). Same rationale as
        add-photo-columns above. email_verified defaults to TRUE in this
        migration specifically (unlike the model's Python-side default of
        False) so existing accounts on a live database are grandfathered
        in as already-verified rather than retroactively locked out of
        login -- only newly-registered accounts (created through
        register(), which explicitly passes email_verified=False) start
        unverified. Safe to re-run (IF NOT EXISTS). Not needed for a
        brand-new database -- init-db already creates the columns there
        (with no rows to grandfather, the model's False default is fine)."""
        with app.app_context():
            db.session.execute(db.text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS email_verified '
                "BOOLEAN NOT NULL DEFAULT TRUE"
            ))
            db.session.execute(db.text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS email_verify_token VARCHAR(64)'
            ))
            db.session.execute(db.text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS '
                "email_verify_token_created_at TIMESTAMP"
            ))
            db.session.commit()
        print("Email verification columns added.")

    @app.cli.command("add-pattern-visibility-columns")
    def add_pattern_visibility_columns():
        """`flask --app wsgi add-pattern-visibility-columns` -- one-off,
        idempotent migration for the private-patterns/sharing feature:
        adds Pattern.is_public, and swaps the old single-column unique
        constraint on original_url (one canonical row per URL, globally,
        always) for a composite one on (original_url, uploader_id) --
        see Pattern.find_duplicate's docstring in models.py for why. The
        new PatternShare table itself doesn't need a migration here:
        db.create_all() (re-run `init-db`, safe, only creates missing
        tables) already creates it on the live database.

        is_public defaults to TRUE in this migration specifically (unlike
        the model's Python-side default of False), same "grandfather
        existing rows in, gate only what's new" split as
        add-email-verification-columns above -- patterns that were already
        community-visible before this feature existed shouldn't suddenly
        disappear from it. Safe to re-run: the constraint swap is wrapped
        so re-running it after it's already applied is a no-op rather than
        an error. Not needed for a brand-new database -- init-db already
        creates both the column and the composite constraint there."""
        with app.app_context():
            db.session.execute(db.text(
                'ALTER TABLE pattern ADD COLUMN IF NOT EXISTS is_public '
                "BOOLEAN NOT NULL DEFAULT TRUE"
            ))
            db.session.execute(db.text(
                "ALTER TABLE pattern DROP CONSTRAINT IF EXISTS pattern_original_url_key"
            ))
            db.session.execute(db.text("""
                DO $$ BEGIN
                    ALTER TABLE pattern ADD CONSTRAINT uq_pattern_original_url_uploader
                        UNIQUE (original_url, uploader_id);
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;
            """))
            db.session.commit()
        print("Pattern visibility columns added. Run `init-db` too if you haven't -- it creates the new pattern_share table.")

    @app.cli.command("add-sharing-and-notification-columns")
    def add_sharing_and_notification_columns():
        """`flask --app wsgi add-sharing-and-notification-columns` --
        one-off, idempotent migration for edit-level pattern sharing and
        per-user notification settings: adds PatternShare.can_edit and
        User.notification_settings. The new notification table itself
        doesn't need a migration here -- db.create_all() (re-run
        `init-db`, safe) already creates it on the live database. Safe to
        re-run (IF NOT EXISTS). Not needed for a brand-new database --
        init-db already creates both columns there."""
        with app.app_context():
            db.session.execute(db.text(
                "ALTER TABLE pattern_share ADD COLUMN IF NOT EXISTS can_edit "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            db.session.execute(db.text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS notification_settings JSON'
            ))
            db.session.commit()
        print("Sharing/notification columns added. Run `init-db` too if you haven't -- it creates the new notification table.")

    @app.cli.command("make-admin")
    @click.argument("email")
    def make_admin(email):
        """`flask --app wsgi make-admin <email>` -- grant one user
        permission to edit ANY pattern, not just their own uploads (see
        _can_edit in patterns/routes.py). Deliberately a CLI command
        rather than a hardcoded email comparison in route logic, so it's
        not tied to one specific address in the codebase."""
        from .models import User

        with app.app_context():
            user = User.query.filter_by(email=email.strip().lower()).first()
            if not user:
                print(f"No user found with email {email}")
                return
            user.is_admin = True
            db.session.commit()
            print(f"{user.username} ({email}) is now an admin.")

    @app.cli.command("seed-e2e")
    def seed_e2e():
        """`flask --app wsgi seed-e2e` -- wipe and recreate the database
        (whatever DATABASE_URL currently points at -- meant to be run only
        against a throwaway e2e DB, never a real one) with a fixed set of
        users/patterns the Playwright e2e suite (frontend/e2e/) references
        by exact username/title. Bypasses register()/scraping/Gemini
        entirely (direct model inserts) so seeding never depends on those
        services being reachable. Safe to re-run -- always starts from a
        clean slate."""
        from .models import Pattern, PatternShare, User

        with app.app_context():
            db.drop_all()
            db.create_all()

            def make_user(username, email, is_admin=False, notification_settings=None):
                user = User(
                    username=username,
                    email=email,
                    password_hash=bcrypt.generate_password_hash("password123").decode("utf-8"),
                    email_verified=True,
                    is_admin=is_admin,
                    notification_settings=notification_settings,
                )
                db.session.add(user)
                return user

            admin = make_user("e2e_admin", "admin@e2e.test", is_admin=True)
            alice = make_user("e2e_alice", "alice@e2e.test")
            bob = make_user("e2e_bob", "bob@e2e.test")
            # email off, in_app on for pattern_shared -- e2e_carol is the
            # fixture notifications.spec.ts uses to assert a disabled email
            # channel actually suppresses the send while in-app still fires.
            carol = make_user(
                "e2e_carol", "carol@e2e.test",
                notification_settings={"pattern_shared": {"email": False, "in_app": True}},
            )
            db.session.flush()

            instructions = {"Part 1: Cast On": ["Cast on 20 stitches.", "Knit 2 rows."]}

            english_pattern = Pattern(
                original_url="https://example.test/e2e-english-pattern",
                title="E2E English Pattern",
                materials="4mm needles, worsted weight yarn",
                abbreviations="k: knit, p: purl",
                instructions=instructions,
                uploader_id=alice.id,
                is_public=True,
                title_he="תבנית לדוגמה באנגלית",
                materials_he="מסרגות 4 מ״מ, חוט עבה",
                abbreviations_he="k: קשירה, p: פרל",
                instructions_he={
                    "Part 1: Cast On": {
                        "heading_he": "חלק 1: הטלת עיניים",
                        "steps_he": ["הטל 20 עיניים.", "סרוג 2 שורות."],
                    }
                },
                translation_reviewed=True,
            )

            hebrew_pattern = Pattern(
                original_url="https://example.test/e2e-hebrew-pattern",
                title="תבנית עברית לבדיקה",
                materials="מסרגות 5 מ״מ",
                abbreviations="ע: עין",
                instructions=instructions,
                uploader_id=alice.id,
                is_public=True,
                title_en="E2E Hebrew Pattern",
                materials_en="5mm needles",
                abbreviations_en="st: stitch",
                instructions_en={
                    "Part 1: Cast On": {
                        "heading_en": "Part 1: Cast On",
                        "steps_en": ["Cast on 20 stitches.", "Knit 2 rows."],
                    }
                },
                translation_en_reviewed=True,
            )

            private_shared_pattern = Pattern(
                original_url="https://example.test/e2e-private-shared-pattern",
                title="E2E Private Shared Pattern",
                materials="Test materials",
                instructions=instructions,
                uploader_id=alice.id,
                is_public=False,
            )

            editable_shared_pattern = Pattern(
                original_url="https://example.test/e2e-editable-shared-pattern",
                title="E2E Editable Shared Pattern",
                materials="Test materials",
                instructions=instructions,
                uploader_id=alice.id,
                is_public=False,
            )

            permissions_pattern = Pattern(
                original_url="https://example.test/e2e-permissions-pattern",
                title="E2E Permissions Pattern",
                materials="Test materials",
                instructions=instructions,
                uploader_id=bob.id,
                is_public=True,
            )

            # Dedicated to the publish/unpublish test in sharing.spec.ts --
            # kept separate from private_shared_pattern/editable_shared_pattern
            # (which sharing.spec.ts's share/unshare tests mutate) so toggling
            # visibility here can never affect another test's fixture state.
            unpublished_pattern = Pattern(
                original_url="https://example.test/e2e-unpublished-pattern",
                title="E2E Unpublished Pattern",
                materials="Test materials",
                instructions=instructions,
                uploader_id=alice.id,
                is_public=False,
            )

            # Dedicated to notifications.spec.ts's share-triggered
            # in-app-notification tests -- kept separate from every other
            # private pattern above so sharing them with bob/carol there
            # can never change the share list another spec (sharing.spec.ts)
            # asserts against.
            notification_pattern_one = Pattern(
                original_url="https://example.test/e2e-notification-pattern-one",
                title="E2E Notification Pattern One",
                materials="Test materials",
                instructions=instructions,
                uploader_id=alice.id,
                is_public=False,
            )
            notification_pattern_two = Pattern(
                original_url="https://example.test/e2e-notification-pattern-two",
                title="E2E Notification Pattern Two",
                materials="Test materials",
                instructions=instructions,
                uploader_id=alice.id,
                is_public=False,
            )

            db.session.add_all([
                english_pattern, hebrew_pattern, private_shared_pattern,
                editable_shared_pattern, permissions_pattern, unpublished_pattern,
                notification_pattern_one, notification_pattern_two,
            ])
            db.session.flush()

            db.session.add(PatternShare(pattern_id=private_shared_pattern.id, user_id=bob.id, can_edit=False))
            db.session.add(PatternShare(pattern_id=editable_shared_pattern.id, user_id=bob.id, can_edit=True))

            db.session.commit()
            print(
                f"Seeded e2e database: users [{admin.username}, {alice.username}, "
                f"{bob.username}, {carol.username}], 8 patterns."
            )

    @app.cli.command("e2e-verify-token")
    @click.argument("email")
    def e2e_verify_token(email):
        """`flask --app wsgi e2e-verify-token <email>` -- print that user's
        current email_verify_token, for the Playwright e2e suite to verify
        a freshly-registered account without needing real email delivery
        (real Resend keys are deliberately out of scope for e2e -- see
        frontend/e2e/). Prints nothing (exit 0) if the user doesn't exist
        or has no pending token."""
        from .models import User

        with app.app_context():
            user = User.query.filter_by(email=email.strip().lower()).first()
            if user and user.email_verify_token:
                print(user.email_verify_token)

    @app.route("/api/health")
    def health():
        return {"status": "ok"}

    @app.errorhandler(413)
    def request_too_large(_error):
        # Every route on this API returns JSON; without this handler,
        # Flask's default 413 (from MAX_CONTENT_LENGTH, see config.py) would
        # be an HTML page instead, which the frontend's `response.json()`
        # can't parse.
        return jsonify({
            "error": "That file is too large (max 5MB).",
            "code": "file_too_large",
            "max_mb": 5,
        }), 413

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        """
        Serve the built React app for every route that isn't one of the
        API routes above. This never intercepts /api/* -- Werkzeug always
        matches a blueprint's literal route (e.g. /api/profile) before
        this catch-all <path:...> converter, regardless of registration
        order, since literal segments are more specific.

        Client-side routes like /pattern/5 aren't real files on disk, so
        any requested path that doesn't correspond to an actual built
        asset falls back to index.html and React Router takes over from
        there once it loads.
        """
        if not FRONTEND_DIST.is_dir():
            return jsonify({
                "error": "Frontend build not found. Run `npm run build` in frontend/ first.",
            }), 404

        requested = FRONTEND_DIST / path if path else None
        if requested and requested.is_file():
            return send_from_directory(FRONTEND_DIST, path)
        return send_from_directory(FRONTEND_DIST, "index.html")

    return app
