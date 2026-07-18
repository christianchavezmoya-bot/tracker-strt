"""
HOLO-RTLS — Flask Extensions
Single init point for all Flask extensions.
Import these in models.py, routes, and services — never re-instantiate.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_mail import Mail

# ── Core ────────────────────────────────────────────────────────────────────
db = SQLAlchemy()          # Database ORM
migrate = Migrate()       # Alembic migrations
jwt = JWTManager()         # JWT token management
mail = Mail()              # Email sending
