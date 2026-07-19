"""
HOLO-RTLS — Application Configuration
All settings loaded from environment variables (never hardcoded).
"""
import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent          # /workspace/HOLO-RTLS
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── Database ────────────────────────────────────────────────────────────────
SQLALCHEMY_DATABASE_URI = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DATA_DIR / 'holo_rtls.db'}"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = os.getenv("SQLALCHEMY_ECHO", "0") == "1"

# ── Secret Keys ─────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable is required")

# ── JWT Settings ────────────────────────────────────────────────────────────
JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", 240)) * 60   # seconds
JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv("JWT_REFRESH_TOKEN_DAYS", 7)) * 86400     # seconds
JWT_TOKEN_LOCATION = ["headers"]
JWT_HEADER_NAME = "Authorization"
JWT_HEADER_TYPE = "Bearer"

# ── Security ────────────────────────────────────────────────────────────────
# Argon2 hashing parameters (industry standard, winner of PHC)
ARGON2_MEMORY_COST = 65536      # 64 MB
ARGON2_TIME_COST = 3            # iterations
ARGON2_PARALLELISM = 4          # threads

# Login lockout
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", 3))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", 300))   # 5 minutes

# Password reset token expiry
PASSWORD_RESET_TOKEN_EXPIRES = int(os.getenv("PASSWORD_RESET_TOKEN_MINUTES", 60)) * 60

# ── Mail / SMTP ──────────────────────────────────────────────────────────────
MAIL_ENABLED = os.getenv("MAIL_ENABLED", "0") == "1"
MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "1") == "1"
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "alerts@holo-rtls.local")
FLASK_MAIL_SUPPRESS_SEND = os.getenv("FLASK_MAIL_SUPPRESS_SEND", "0") == "1"   # Dev mode

# ── SMS (Twilio) ───────────────────────────────────────────────────────────
SMS_ENABLED = os.getenv("SMS_ENABLED", "0") == "1"
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")

# ── MQTT ─────────────────────────────────────────────────────────────────────
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", 1883))
MQTT_BROKER_USERNAME = os.getenv("MQTT_BROKER_USERNAME", "")
MQTT_BROKER_PASSWORD = os.getenv("MQTT_BROKER_PASSWORD", "")
MQTT_USE_TLS = os.getenv("MQTT_USE_TLS", "0") == "1"
MQTT_TLS_INSECURE = os.getenv("MQTT_TLS_INSECURE", "0") == "1"

# ── UWB / Positioning ────────────────────────────────────────────────────────
USE_MOCK_UWB = os.getenv("USE_MOCK_UWB", "1") == "1"
UWB_SERIAL_PORT = os.getenv("UWB_SERIAL_PORT", "/dev/ttyUSB0")
UWB_BAUD_RATE = int(os.getenv("UWB_BAUD_RATE", 115200))

# ── File Storage ────────────────────────────────────────────────────────────
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_LOGO_SIZE_MB = int(os.getenv("MAX_LOGO_SIZE_MB", 2))
ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "svg", "webp"}

# ── Backup ───────────────────────────────────────────────────────────────────
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)
BACKUP_RETENTION_COUNT = int(os.getenv("BACKUP_RETENTION_COUNT", 10))

# ── Business Defaults ───────────────────────────────────────────────────────
DEFAULT_FACILITY_NAME = os.getenv("DEFAULT_FACILITY_NAME", "HOLO-RTLS Facility")
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "UTC")
DEFAULT_MAP_SCALE = float(os.getenv("DEFAULT_MAP_SCALE", 100))   # pixels per meter

# Alert thresholds
DEFAULT_BATTERY_CRITICAL_PCT = int(os.getenv("DEFAULT_BATTERY_CRITICAL_PCT", 15))
DEFAULT_NO_SIGNAL_TIMEOUT_SECS = int(os.getenv("DEFAULT_NO_SIGNAL_TIMEOUT_SECS", 120))
DEFAULT_NO_MOVEMENT_THRESHOLD_M = float(os.getenv("DEFAULT_NO_MOVEMENT_THRESHOLD_M", 0.5))
DEFAULT_NO_MOVEMENT_CHECK_INTERVAL_SECS = int(os.getenv("DEFAULT_NO_MOVEMENT_CHECK_INTERVAL_SECS", 300))

# ── Application ─────────────────────────────────────────────────────────────
APP_NAME = "HOLO-RTLS"
APP_VERSION = "1.0.0"
DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
TESTING = False

# ── Pagination ───────────────────────────────────────────────────────────────
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")   # Restrict in production

# ── Security / Rate Limiting ────────────────────────────────────────────────
RATE_LIMIT_STORAGE = os.getenv("RATE_LIMIT_STORAGE", "memory://")  # Use Redis URI for production
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "200/minute")
RATE_LIMIT_AUTH = os.getenv("RATE_LIMIT_AUTH", "10/minute")
RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "5/minute")
RATE_LIMIT_STRICT = os.getenv("RATE_LIMIT_STRICT", "1/minute")

# ── Database Pool ────────────────────────────────────────────────────────────
# Defined here for reference; applied in app.py after URI is resolved
# (pool options are invalid for SQLite :memory: used in tests)
SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_size": int(os.getenv("DB_POOL_SIZE", 10)),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", 20)),
    "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", 3600)),
    "pool_pre_ping": True,
    "echo": os.getenv("SQLALCHEMY_ECHO", "0") == "1",
}

# ── Compression ──────────────────────────────────────────────────────────────
COMPRESS_ENABLED = os.getenv("COMPRESS_ENABLED", "1") == "1"
