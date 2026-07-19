"""
HOLO-RTLS — Security Middleware
Rate limiting, security headers, CORS, and input validation.
Imported and configured in app.py.
"""
from __future__ import annotations
import os, re
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_compress import Compress

# ── Rate Limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=["200 per minute"],
    strategy="fixed-window",
)


def get_limiter() -> Limiter:
    return limiter


# ── Security headers via Talisman ─────────────────────────────────────────────
CSP_POLICY = {
    "default-src": "'self'",
    "script-src": "'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com",
    "style-src": "'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://unpkg.com",
    "font-src": "'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com",
    "img-src": "'self' data: blob: https://unpkg.com",
    "connect-src": "'self' ws: wss:",
    "frame-ancestors": "'none'",
    "form-action": "'self'",
    "base-uri": "'self'",
    "object-src": "'none'",
}


def init_talisman(app: Flask) -> Talisman:
    if app.config.get("TESTING"):
        # Skip CSP in test mode to avoid errors
        return Talisman(app, force_https=False)

    return Talisman(
        app,
        content_security_policy=CSP_POLICY,
        force_https=False,
        frame_options="DENY",
        x_content_type_options="nosniff",
        x_xss_protection=True,
        referrer_policy="strict-origin-when-cross-origin",
        permissions_policy="geolocation=(), microphone=(), camera=()",
    )


# ── Response compression ─────────────────────────────────────────────────────────
def init_compress(app: Flask) -> Compress:
    Compress(app)
    return app


# ── Input Validation ─────────────────────────────────────────────────────────────
class ValidationError(Exception):
    def __init__(self, message, field=None):
        self.message = message
        self.field = field
        super().__init__(message)


def sanitize_string(value: str, max_length: int = 500) -> str:
    """Strip and truncate a string, removing control characters."""
    if not isinstance(value, str):
        return ""
    # Remove control characters except newlines/tabs
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    return value.strip()[:max_length]


def sanitize_mac(value: str) -> str:
    """Validate and sanitize a MAC address."""
    if not value:
        return ""
    # Allow colons, hyphens, or no separator
    cleaned = re.sub(r"[^0-9A-Fa-f:.-]", "", value.upper())
    if len(cleaned) not in (12, 17):
        raise ValidationError("Invalid MAC address format", field="hardware_id")
    return cleaned


def sanitize_email(value: str) -> str:
    """Basic email sanitization."""
    value = sanitize_string(value, 254).lower()
    if value and not re.match(r"^[^@]+@[^@]+\.[^@]+$", value):
        raise ValidationError("Invalid email address", field="email")
    return value


def sanitize_username(value: str) -> str:
    """Sanitize username: alphanumeric, underscore, hyphen, 3-64 chars."""
    value = sanitize_string(value, 64)
    if not re.match(r"^[a-zA-Z0-9_-]{3,64}$", value):
        raise ValidationError(
            "Username must be 3–64 characters, alphanumeric, underscore, or hyphen",
            field="username"
        )
    return value


def sanitize_json_body(body: dict, fields: dict) -> dict:
    """
    Sanitize a JSON request body.

    fields: dict of field_name → (type, max_length)
    type options: 'string', 'email', 'username', 'mac', 'int', 'float', 'bool'
    """
    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object")
    result = {}
    for field, (field_type, max_len) in fields.items():
        value = body.get(field)
        if value is None:
            continue
        try:
            if field_type == "string":
                result[field] = sanitize_string(str(value), max_len)
            elif field_type == "email":
                result[field] = sanitize_email(str(value))
            elif field_type == "username":
                result[field] = sanitize_username(str(value))
            elif field_type == "mac":
                result[field] = sanitize_mac(str(value))
            elif field_type == "int":
                result[field] = int(value)
            elif field_type == "float":
                result[field] = float(value)
            elif field_type == "bool":
                result[field] = bool(value)
            else:
                result[field] = value
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Invalid value for {field}: {e}", field=field)
    return result


# ── SQL Injection helpers ───────────────────────────────────────────────────────
# SQLAlchemy uses parameterized queries — this is a belt-and-suspenders check.
# Never concatenate user input directly into SQL strings.
FORBIDDEN_SQL_CHARS = re.compile(r"[\x00\n\r\x1a;']")


def safe_identifier(value: str, allow_list: list | None = None) -> str:
    """Ensure a value is a safe SQL identifier (table/column name)."""
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$", value):
        raise ValidationError(f"Invalid identifier: {value}")
    if allow_list and value not in allow_list:
        raise ValidationError(f"Identifier '{value}' not in allow list")
    return value
