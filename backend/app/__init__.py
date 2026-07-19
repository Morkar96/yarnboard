"""
Application factory.

create_app() builds and configures the Flask app: loads config, wires up
the shared extensions (db, bcrypt), enables CORS for the separately-hosted
React frontend, and registers the two blueprints that hold all the actual
routes. Keeping route logic out of this file (in auth/routes.py and
patterns/routes.py) is what the "auth" vs "patterns" split buys us: each
blueprint is a self-contained module you can read top-to-bottom for one
concern, without wading through the other.
"""

import os

from flask import Flask, jsonify
from flask_cors import CORS

from .config import get_config
from .extensions import db, bcrypt


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

    return app
