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
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
bcrypt = Bcrypt()

# In-memory storage (the default) is fine for this app's single-service,
# low-traffic deployment -- it resets on restart and isn't shared across
# worker processes, which is an acceptable tradeoff here since the goal is
# blunting casual brute-force/credential-stuffing/email-bombing attempts,
# not perfect enforcement. Default limits are applied per-route below
# (see auth/routes.py) rather than globally, since most routes don't need
# throttling as tightly as login/register do.
limiter = Limiter(key_func=get_remote_address)
