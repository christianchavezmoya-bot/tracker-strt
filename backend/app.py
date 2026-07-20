"""
HOLO-RTLS — Flask Application Factory
"""
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flasgger import Swagger

from backend import config
from backend.extensions import db, migrate, jwt, mail
from backend.security import init_talisman, init_compress, limiter, ValidationError


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
    app.config["JWT_TOKEN_LOCATION"] = config.JWT_TOKEN_LOCATION
    app.config["JWT_QUERY_STRING_NAME"] = config.JWT_QUERY_STRING_NAME

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

    # Set engine options AFTER URI is resolved (handles test :memory: overrides)
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    is_sqlite = db_uri.startswith(("sqlite:", "sqlite3:"))
    if not is_sqlite:
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_size": int(os.getenv("DB_POOL_SIZE", 10)),
            "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", 20)),
            "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", 3600)),
            "pool_pre_ping": True,
            "echo": app.config.get("SQLALCHEMY_ECHO", False),
        }
    else:
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {}

    # ── Initialize extensions ──────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    mail.init_app(app)

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS(app, resources={r"/api/*": {"origins": config.CORS_ORIGINS}},
         expose_headers=["X-Request-Id", "X-RateLimit-Limit", "X-RateLimit-Remaining"])

    # ── Security headers (CSP, HSTS, etc.) ────────────────────────────────────
    init_talisman(app)

    # ── Rate limiting ────────────────────────────────────────────────────────
    if not test_config:
        limiter.storage_uri = config.RATE_LIMIT_STORAGE
        limiter._default_limits = [config.RATE_LIMIT_DEFAULT]
    limiter.init_app(app)

    # ── Compression ───────────────────────────────────────────────────────────
    if not test_config and config.COMPRESS_ENABLED:
        init_compress(app)

    # ── Global error handlers ────────────────────────────────────────────────
    @app.errorhandler(ValidationError)
    def handle_validation_error(e):
        return jsonify({"error": e.message, "field": e.field}), 400

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify({
            "error": "Rate limit exceeded",
            "retry_after": e.description,
        }), 429

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
    from backend.api.stream import stream_bp
    from backend.api.positioning import positioning_bp
    from backend.api.scanner import scanner_bp
    from backend.api.keys import keys_bp
    from backend.api.checkin import checkin_bp
    from backend.api.sessions import sessions_bp
    from backend.api.webhooks import webhooks_bp, schedules_bp
    from backend.api.inject import inject_bp
    from backend.api.push import push_bp

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
    app.register_blueprint(positioning_bp)
    app.register_blueprint(scanner_bp)
    app.register_blueprint(stream_bp)
    app.register_blueprint(keys_bp)
    app.register_blueprint(checkin_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(schedules_bp)
    app.register_blueprint(inject_bp)
    app.register_blueprint(push_bp)

    if os.getenv("PLAYWRIGHT_E2E") == "1":
        from backend.api.e2e import e2e_bp
        app.register_blueprint(e2e_bp)

    # ── JWT blocklist (session revoke) ────────────────────────────────────────
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        from backend.api.sessions import is_jti_revoked
        return is_jti_revoked(jwt_payload.get("jti"))

    # ── API key middleware (X-API-Key on selected routes) ──────────────────────
    @app.before_request
    def api_key_auth_optional():
        """Allow X-API-Key as alternative auth for /api/trackers, /api/alerts, inject."""
        if not request.path.startswith("/api/"):
            return None
        raw = request.headers.get("X-API-Key")
        if not raw:
            return None
        import hashlib
        from backend.models import ApiKey
        from datetime import datetime, timezone
        h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        key = ApiKey.query.filter_by(key_hash=h, is_active=True).first()
        if not key or key.is_expired():
            return jsonify({"error": "Invalid API key"}), 401
        key.last_used_at = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        request.api_key = key
        request.current_user_id = key.user_id
        return None

    # ── Frontend routes ───────────────────────────────────────────────────────
    from flask import render_template

    @app.route("/")
    def index():
        return render_template("dashboard/index.html")

    @app.route("/login")
    def login_page():
        return render_template("auth/login.html")

    @app.route("/reset-password")
    def reset_password_page():
        return render_template("auth/reset_password.html")

    @app.route("/trackers")
    def trackers_page():
        return render_template("dashboard/trackers.html")

    @app.route("/integrations")
    def integrations_page():
        return render_template("dashboard/integrations.html")

    @app.route("/muster")
    def muster_page():
        return render_template("dashboard/muster.html")

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
        return render_template("hardware/index.html")

    @app.route("/tracking")
    def tracking_page():
        """Legacy scanner lab retired — Location Core lives on Live Map Setup."""
        from flask import redirect
        return redirect("/?mode=setup", code=302)

    @app.route("/nodes")
    def nodes_page():
        return render_template("nodes/index.html")

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

    # ── Lightweight health (no auth) for probes ───────────────────────────────
    @app.route("/health")
    @app.route("/api/health")
    def health():
        return jsonify({"ok": True, "service": "holo-rtls"}), 200

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
        from backend.models import (
            User, Tracker, WifiNode, MapSection, Zone,
            Alert, Notification, AuditLog, Setting,
        )
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

    # ── Phase 3: Positioning Engine ────────────────────────────────────────────
    # HOLO_SKIP_INIT=1 lets `flask db ...` CLI load the app without running the
    # positioning bootstrap (which would create_all/start threads).
    if not test_config and os.getenv("HOLO_SKIP_INIT") != "1":
        with app.app_context():
            _init_positioning(app)

    if not test_config and not config.DEBUG:
        import logging
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if str(uri).startswith("sqlite"):
            logging.getLogger(__name__).warning(
                "SQLite in non-debug mode — use PostgreSQL for production (docs/POSTGRES.md)"
            )

    return app


def _init_positioning(app):
    import logging
    logger = logging.getLogger(__name__)

    from backend.models.positioning import TrackingHistory, PositionSnapshot
    db.create_all()
    _ensure_schema_columns()

    _seed_demo_if_needed(app)

    from backend.services.positioning_service import PositioningService
    from backend.services.floor_plan_mapper import FloorPlanMapperService
    from backend.services.history_service import init_history_service
    from backend.services.hardware_bridge import HardwareBridgeManager
    from backend.services.ingestion_loop import start_ingestion
    from backend.api.stream import init_mqtt_publisher
    from backend.services.notification_service import init_notification_service
    from backend.services.alert_service import init_alert_service
    import backend.config as cfg

    pos_svc = PositioningService(db.session)
    anchors_loaded = pos_svc.load_anchors_from_db()
    anchors = dict(pos_svc._anchors)

    mapper_svc = FloorPlanMapperService(db.session)

    history_svc = init_history_service(db.session, app=app, retention_days=30, flush_interval=5)
    history_svc.start()

    # Notification service (email/SMS dispatch)
    notif_svc = init_notification_service(db.session, app)

    # Alert service (zone evaluation, offline checks)
    alert_svc = init_alert_service(
        db.session, app,
        no_signal_timeout=int(getattr(cfg, 'NO_SIGNAL_TIMEOUT', 120)),
    )
    alert_svc.start()

    try:
        from backend.services.scheduler_service import init_scheduler
        init_scheduler(app)
    except Exception as e:
        logger.warning(f"Scheduler not started: {e}")

    try:
        mqtt_pub = init_mqtt_publisher(
            getattr(cfg, 'MQTT_BROKER_HOST', 'localhost'),
            int(getattr(cfg, 'MQTT_BROKER_PORT', 1883)),
            getattr(cfg, 'MQTT_USERNAME', None),
            getattr(cfg, 'MQTT_PASSWORD', None),
        )
        logger.info(f"MQTT publisher: {getattr(cfg, 'MQTT_BROKER_HOST', 'localhost')}")
    except Exception as e:
        logger.warning(f"MQTT not configured: {e}")
        mqtt_pub = None

    bridge_mgr = HardwareBridgeManager(db.session, app)
    bridge_mgr.start_all(anchors=anchors)

    ingestion = start_ingestion(
        app=app, bridge_manager=bridge_mgr,
        positioning_service=pos_svc, history_service=history_svc,
        floor_plan_mapper=mapper_svc, mqtt_client=mqtt_pub,
        alert_service=alert_svc,
    )

    logger.info(
        f"HOLO-RTLS online — {anchors_loaded} anchors, "
        f"{len(bridge_mgr._bridges)} bridges, "
        f"alerts: {'running' if alert_svc else 'disabled'}, "
        f"ingestion: {'running' if ingestion else 'FAILED'}"
    )


def _ensure_schema_columns():
    """Auto-add any model columns missing from existing tables so additive model
    changes never break an existing SQLite DB (create_all can't ALTER, and adding
    a column to a model without a migration is the common cause of
    'no such column' on startup).

    Handles the additive case generically for every mapped table. Drops, renames
    and type changes still need a real migration. Set AUTO_SCHEMA_RECONCILE=0 to
    disable (e.g. when managing schema with `flask db upgrade` — see docs/MIGRATIONS.md).
    """
    import os as _os
    import logging
    from sqlalchemy import text, inspect
    log = logging.getLogger(__name__)
    if _os.getenv("AUTO_SCHEMA_RECONCILE", "1") != "1":
        return
    try:
        insp = inspect(db.engine)
        existing = set(insp.get_table_names())
        dialect = db.engine.dialect
        for table in db.metadata.sorted_tables:
            if table.name not in existing:
                continue  # brand-new tables are handled by create_all()
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                try:
                    coltype = col.type.compile(dialect=dialect)
                except Exception:
                    coltype = "TEXT"
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
                sd = getattr(col, "server_default", None)
                if sd is not None and getattr(sd, "arg", None) is not None:
                    txt = getattr(sd.arg, "text", sd.arg)
                    ddl += f" DEFAULT {txt}"
                try:
                    with db.engine.begin() as conn:
                        conn.execute(text(ddl))
                    log.info("Schema reconcile: added %s.%s", table.name, col.name)
                except Exception as e:
                    log.warning("Schema reconcile: could not add %s.%s (%s)", table.name, col.name, e)
    except Exception as e:
        log.warning("Schema reconcile skipped: %s", e)


def _seed_demo_if_needed(app):
    """Ensure admin + mock simulator exist so Live Map works on first boot."""
    import logging
    from backend.models import User, UserRole, HardwareConfig, WifiNode, Tracker, Setting
    from backend.models.settings import SettingScope
    from backend.services.settings_defaults import SETTING_DEFAULTS
    from backend.models.hardware import ConnectionStatus, HardwareType, Protocol
    from backend.models.tracker import TagType, DeviceCategory, NodeType, NodeStatus

    log = logging.getLogger(__name__)

    if User.query.count() == 0:
        admin = User(
            email="admin@holo-rtls.local",
            username="admin",
            display_name="System Administrator",
            role=UserRole.ADMIN,
        )
        admin.set_password("ChangeMe123!")
        db.session.add(admin)
        log.info("Seeded default admin user")

    demo_nodes = [
        ("AA:00:00:00:00:01", "Demo Anchor N", 0.0, 0.0, 2.5),
        ("AA:00:00:00:00:02", "Demo Anchor E", 20.0, 0.0, 2.5),
        ("AA:00:00:00:00:03", "Demo Anchor S", 20.0, 15.0, 2.5),
        ("AA:00:00:00:00:04", "Demo Anchor W", 0.0, 15.0, 2.5),
    ]
    for mac, name, x, y, z in demo_nodes:
        if not WifiNode.query.filter_by(mac_address=mac).first():
            db.session.add(WifiNode(
                mac_address=mac, assigned_name=name,
                pos_x=x, pos_y=y, pos_z=z,
                node_type=int(NodeType.STANDARD),
                status=int(NodeStatus.ACTIVE),
            ))

    for hid, name, tt, cat in [
        ("TAG_001", "Operator Alpha", TagType.PERSONNEL, DeviceCategory.PERSONNEL_TAG),
        ("TAG_002", "Machine Cart B", TagType.MACHINE, DeviceCategory.MACHINE_TAG),
        ("TAG_003", "Sensor Pack C", TagType.PERSONNEL, DeviceCategory.ENV_SENSOR),
    ]:
        if not Tracker.query.filter_by(hardware_id=hid).first():
            db.session.add(Tracker(
                hardware_id=hid, assigned_name=name,
                tag_type=int(tt), category=int(cat),
            ))

    # Prefer an active mock_data bridge for demos when none exists
    has_mock = HardwareConfig.query.filter_by(profile_id="mock_data").first()
    if not has_mock:
        mock = HardwareConfig(
            name="Demo Mock Simulator",
            hardware_type=HardwareType.UWB,
            protocol=Protocol.SERIAL,
            profile_id="mock_data",
            is_active=True,
            status=ConnectionStatus.DISCONNECTED,
        )
        mock.set_settings({"interval": 0.5, "tracker_ids": "TAG_001,TAG_002,TAG_003"})
        db.session.add(mock)
        log.info("Seeded demo mock_data hardware config")

    for key, meta in SETTING_DEFAULTS.items():
        if not Setting.query.filter_by(key=key).first():
            db.session.add(Setting(
                key=key,
                value=meta["value"],
                value_type=meta["value_type"],
                scope=int(meta["scope"]),
                label=meta.get("label"),
            ))

    db.session.commit()

