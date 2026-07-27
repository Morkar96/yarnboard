"""
Shared pytest fixtures: a fresh Flask app + a fresh temp-file SQLite
database for every single test function.

A temp *file* (not sqlite:///:memory:) is used deliberately -- an
in-memory SQLite database is scoped to a single connection, and
Flask-SQLAlchemy's connection pooling means the app and the test code can
easily end up on two different connections to two different (both empty)
in-memory databases. A temp file sidesteps that entirely at negligible
cost (fast local disk, auto-cleaned after each test).

SQLALCHEMY_DATABASE_URI is overridden on `app.config` *after* create_app()
runs, not via the DATABASE_URL environment variable -- app/config.py reads
that env var once, as a class attribute, at import time, so setting it
per-test would only affect whichever test happens to run first. Flask-
SQLAlchemy resolves the engine lazily from `app.config`, so overriding it
here still takes effect for this app instance.
"""

import os
import tempfile

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture()
def app():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")

    flask_app = create_app()
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
    )

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
