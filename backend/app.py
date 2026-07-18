"""
HOLO-RTLS — Flask Application Factory
"""
import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flasgger import Swagger

from backend import config
from backend.extensions import db, migrate, jwt, mail


def create_app(test_config: dict = None) -> Flask:
    """
    Application factory.
    Call this once in run.py (production) or conftest.py (tests).
    """
    app = Flask(
        __name__,
        template_folder="../frontend/templates",
        static_folder="../frontend/static",
        static_url_path="/static",
    )

    # ── Load configuration ────────────────────────────────────────────────────
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = config.SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = config.SQLALCHEMY_TRACK_MODIFICATIONS
    app.config["SQLALCHEMY_ECHO"] = config.SQLALCHEMY_ECHO
    app.config["JWT_SECRET_KEY"] = config.JWT_SECRET_KEY
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = config.JWT_ACCESS_TOKEN_EXPIRES
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = config.JWT_REFRESH_TOKEN_EXPIRES

    # Mail
    app.config["MAIL_SERVER"] = config.MAIL_SERVER
    app.config["MAIL_PORT"] = config.MAIL_PORT
    app.config["MAIL_USE_TLS"] = config.MAIL_USE_TLS
    app.config["MAIL_USERNAME"] = config.MAIL_USERNAME
    app.config["MAIL_PASSWORD"] = config.MAIL_PASSWORD
    app.config["MAIL_DEFAULT_SENDER"] = config.MAIL_DEFAULT_SENDER
    app.config["FLASK_MAIL_SUPPRESS_SEND"] = config.FLASK_MAIL_SUPPRESS_SEND

    if test_config:
        app.config.update(test_config)

    # ── Initialize extensions ──────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    mail.init_app(app)

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS(app, resources={r"/api/*": {"origins": config.CORS_ORIGINS}})

    # ── Swagger / OpenAPI ─────────────────────────────────────────────────────
    if not test_config:
        swagger_config = {
            "headers": [],
            "specs": [
                {
                    "endpoint": "apispec",
                    "route": "/apispec.json",
                    "rule_filter": lambda rule: True,
                    "model_filter": lambda tag: True,
                }
            ],
            "static_url_path": "/flasgger_static",
            "swagger_ui": True,
            "specs_route": "/api/docs",
        }
        swagger_template = {
            "info": {
                "title": "HOLO-RTLS API",
                "description": "Indoor Real-Time Location System — REST API",
                "version": "1.0.0",
            },
            "securityDefinitions": {
                "Bearer": {
                    "type": "apiKey",
                    "name": "Authorization",
                    "in": "header",
                    "description": "JWT Bearer token. Format: 'Bearer <token>'",
                }
            },
        }
        Swagger(app, config=swagger_config, template=swagger_template)

    # ── Register blueprints ────────────────────────────────────────────────────
    from backend.api import auth_bp
    from backend.api.trackers import trackers_bp
    from backend.api.nodes import nodes_bp
    from backend.api.zones import zones_bp
    from backend.api.alerts import alerts_bp
    from backend.api.search import search_bp
    from backend.api.settings import settings_bp
    from backend.api.users import users_bp
    from backend.api.audit import audit_bp
    from backend.api.notifications import notifications_bp
    from backend.api.reports import reports_bp
    from backend.api.backup import backup_bp
    from backend.api.uwb import uwb_bp
    from backend.api.hardware import hardware_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(trackers_bp)
    app.register_blueprint(nodes_bp)
    app.register_blueprint(zones_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(uwb_bp)
    app.register_blueprint(hardware_bp)

    # ── Frontend routes ───────────────────────────────────────────────────────
    from flask import render_template

    @app.route("/")
    def index():
        return render_template("dashboard/index.html")

    @app.route("/login")
    def login_page():
        return render_template("auth/login.html")

    @app.route("/trackers")
    def trackers_page():
        return render_template("dashboard/trackers.html")

    @app.route("/zones")
    def zones_page():
        return render_template("dashboard/zones.html")

    @app.route("/alerts")
    def alerts_page():
        return render_template("dashboard/alerts.html")

    @app.route("/reports")
    def reports_page():
        return render_template("dashboard/reports.html")

    @app.route("/settings")
    def settings_page():
        return render_template("dashboard/settings.html")

    @app.route("/hardware")
    def hardware_page():
        return render_template("dashboard/hardware.html")

    @app.route("/users")
    def users_page():
        return render_template("dashboard/users.html")

    @app.route("/audit")
    def audit_page():
        return render_template("dashboard/audit.html")

    @app.route("/backup")
    def backup_page():
        return render_template("dashboard/backup.html")

    @app.route("/search")
    def search_page():
        return render_template("dashboard/search.html")

    # ── Error handlers ────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return render_template("dashboard/index.html"), 200   # SPA fallback

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({"error": "Too many requests"}), 429

    # ── JWT error handlers ────────────────────────────────────────────────────
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({"error": "Token expired", "code": "token_expired"}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({"error": "Invalid token", "code": "invalid_token"}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({"error": "Authorization required", "code": "authorization_required"}), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({"error": "Token has been revoked", "code": "token_revoked"}), 401

    # ── Shell context (flask shell) ───────────────────────────────────────────
    @app.shell_context_processor
    def make_shell_context():
        from backend.models import *
        return {
            "db": db,
            "User": User,
            "Tracker": Tracker,
            "WifiNode": WifiNode,
            "MapSection": MapSection,
            "Zone": Zone,
            "Alert": Alert,
            "Notification": Notification,
            "AuditLog": AuditLog,
            "Setting": Setting,
        }

    return app
