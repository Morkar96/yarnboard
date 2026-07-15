"""
Environment-driven configuration for the Flask app.

Two config classes are provided (`DevConfig`, `ProdConfig`); `create_app()`
picks one based on the FLASK_ENV environment variable. The main behavioral
difference between them is session cookie security: production runs the
frontend and backend as two separate Render services on different
subdomains, which is a cross-origin setup from the browser's point of view,
so the session cookie must be sent with SameSite=None; Secure. Locally,
both sides run on http://localhost, where that combination doesn't work
(Secure cookies require HTTPS), so dev keeps the ordinary Lax defaults.
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


class DevConfig(BaseConfig):
    DEBUG = True
    # Defaults (Lax, not Secure) are fine for same-site http://localhost dev.


class ProdConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SAMESITE = "None"
    SESSION_COOKIE_SECURE = True


def get_config():
    """Return the config class selected by the FLASK_ENV env var."""
    env = os.environ.get("FLASK_ENV", "development")
    return ProdConfig if env == "production" else DevConfig
