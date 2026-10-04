"""
Shared Flask extension instances.

These are instantiated here (without an app attached) and bound to the real
app later inside create_app() via extension.init_app(app). Keeping them in
their own module -- instead of creating them directly in __init__.py --
lets models.py and scraper.py import `db`/`bcrypt` without importing
app/__init__.py itself, which would otherwise create a circular import
(__init__.py needs models.py to create tables, models.py needs `db`).
"""

from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt

db = SQLAlchemy()
bcrypt = Bcrypt()
