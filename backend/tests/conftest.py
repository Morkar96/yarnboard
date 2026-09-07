"""
Shared pytest fixtures: a fresh Flask app + a fresh temp-file SQLite
database for every single test function.

A temp *file* (not sqlite:///:memory:) is used deliberately -- an
in-memory SQLite database is scoped to a single connection, and
Flask-SQLAlchemy's connection pooling means the app and the test code can
easily end up on two different connections to two different (both empty)
in-memory databases. A temp file sidesteps that entirely at negligible
cost (fast local disk, auto-cleaned after each test).

SQLALCHEMY_DATABASE_URI is passed into create_app()'s config_overrides,
not set via the DATABASE_URL environment variable -- app/config.py reads
that env var once, as a class attribute, at import time, so setting it
per-test would only affect whichever test happens to run first. It also
can't be applied via `app.config.update(...)` *after* create_app()
returns: Flask-SQLAlchemy 3.x builds the engine eagerly inside
`db.init_app(app)` (called from within create_app()), reading
SQLALCHEMY_DATABASE_URI at that exact moment -- a later `.config.update()`
doesn't change which engine `db.create_all()`/`drop_all()` actually use.
Getting this wrong here previously meant every test run was silently
dropping all tables in the real local `backend/instance/yarnboard.db`
instead of an isolated temp file.
"""

import os
import tempfile

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture()
def app():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")

    flask_app = create_app(config_overrides={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        # Rate limiting (see app/extensions.py's `limiter`) is disabled by
        # default for tests: its storage is a single in-memory store
        # shared by the one `Limiter` object across every test's Flask
        # app (Flask-Limiter doesn't scope storage per-app), so without
        # this, request counts would accumulate across unrelated tests in
        # the same pytest run and eventually start 429ing tests that call
        # login()/register() repeatedly. test_security.py re-enables it
        # explicitly (and calls limiter.reset() first) for the tests that
        # actually verify rate-limiting behavior.
        "RATELIMIT_ENABLED": False,
    })

    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture()
def client(app):
    """A Flask test client with cookie persistence across requests, so
    login -> subsequent-authenticated-request flows work the way they do
    in a real browser session."""
    return app.test_client()
