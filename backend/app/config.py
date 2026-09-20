"""
Environment-driven configuration for the Flask app.

Two config classes are provided (`DevConfig`, `ProdConfig`); `create_app()`
picks one based on the FLASK_ENV environment variable. In production the
app is served over real HTTPS, so the session cookie is marked Secure;
it's also marked SameSite=None so it's still sent on credentialed
cross-origin requests. That cross-origin case is real, not
hypothetical: Yarnboard can be deployed either as a single combined
Render service (frontend + /api/* same-origin -- see FRONTEND_DIST in
app/__init__.py) or with the frontend built separately and hosted
elsewhere (e.g. Cloudflare, see README's "Deploying the frontend to
Cloudflare" section) while the API stays on Render, which makes them
different origins. SameSite=None+Secure works correctly for both cases
(browsers still send it same-origin too), so one setting covers both
without needing to know at config time which topology is in use --
CORS_ORIGINS below is the actual origin allowlist either way. Locally
the Vite dev server runs on plain HTTP, where a Secure cookie would
never be sent at all, so dev config leaves the (Lax, non-Secure)
defaults alone.
"""

import os


def _parse_cors_origins(raw: str) -> list[str]:
    """Split a comma-separated CORS_ORIGINS env var into a clean list."""
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


INSECURE_DEFAULT_SECRET_KEY = "dev-secret-key-change-me"


class BaseConfig:
    """Settings shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY", INSECURE_DEFAULT_SECRET_KEY)

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
    # Required alongside Secure for the cookie to be sent on a
    # credentialed cross-origin request (e.g. a Cloudflare-hosted
    # frontend calling the Render-hosted API) -- see the module
    # docstring above. A same-origin deployment still works fine with
    # this set; browsers send SameSite=None cookies same-origin too.
    SESSION_COOKIE_SAMESITE = "None"


def get_config():
    """Return the config class selected by the FLASK_ENV env var."""
    env = os.environ.get("FLASK_ENV", "development")
    return ProdConfig if env == "production" else DevConfig
