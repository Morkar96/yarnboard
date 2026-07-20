"""
Environment-driven configuration for the Flask app.

Two config classes are provided (`DevConfig`, `ProdConfig`); `create_app()`
picks one based on the FLASK_ENV environment variable. Production and dev
differ only in the session cookie's Secure flag: in production the app is
served over real HTTPS (a single Render service serves both the API and
the built frontend -- see FRONTEND_DIST in app/__init__.py -- so this is
always same-origin, Lax is sufficient, no SameSite=None cross-site
workaround needed), whereas locally the Vite dev server runs on plain
HTTP, where a Secure cookie would never be sent at all.
"""

import os


def _parse_cors_origins(raw: str) -> list[str]:
    """Split a comma-separated CORS_ORIGINS env var into a clean list."""
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


class BaseConfig:
    """Settings shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # Neon (or any Postgres) connection string, e.g.
    # postgresql://user:password@host/dbname
    # Falls back to a local SQLite file so the app runs with zero setup.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///yarnboard.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Comma-separated list of origins allowed to make credentialed requests
    # (i.e. the deployed frontend URL(s)).
    CORS_ORIGINS = _parse_cors_origins(
        os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    )

    # Caps every incoming request body, including the HTML file uploads
    # accepted by POST /api/patterns/preview-upload (the fallback for sites
    # whose bot-detection blocks Yarnboard's automatic fetch) -- a saved
    # pattern page is at most a few hundred KB, so 5MB is generous headroom
    # while still guarding against someone uploading something absurd.
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024


class DevConfig(BaseConfig):
    DEBUG = True
    # Defaults (Lax, not Secure) are fine for same-site http://localhost dev.


class ProdConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


def get_config():
    """Return the config class selected by the FLASK_ENV env var."""
    env = os.environ.get("FLASK_ENV", "development")
    return ProdConfig if env == "production" else DevConfig
