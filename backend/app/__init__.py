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

import click
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from .config import get_config
from .extensions import db, bcrypt

# backend/app/__init__.py -> up three levels is the repo root, then into
# the frontend's Vite build output. Doesn't exist until `npm run build`
# has been run (see serve_frontend's 404 fallback for local dev, where the
# Vite dev server is used instead and this path is never populated).
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def create_app():
    app = Flask(__name__)
    app.config.from_object(get_config())

    db.init_app(app)
    bcrypt.init_app(app)

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
