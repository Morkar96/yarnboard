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

    app.register_blueprint(auth_bp)
    app.register_blueprint(patterns_bp)

    @app.cli.command("init-db")
    def init_db():
        """`flask --app wsgi init-db` -- create all tables. Safe to re-run;
        only creates tables that don't already exist. This is the one-off
        substitute for a migration tool, appropriate for this app's size
        (see README for the tradeoff)."""
        with app.app_context():
            db.create_all()
        print("Database tables created.")

    @app.route("/api/health")
    def health():
        return {"status": "ok"}

    @app.errorhandler(413)
    def request_too_large(_error):
        # Every route on this API returns JSON; without this handler,
        # Flask's default 413 (from MAX_CONTENT_LENGTH, see config.py) would
        # be an HTML page instead, which the frontend's `response.json()`
        # can't parse.
        return jsonify({"error": "That file is too large (max 5MB)."}), 413

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
