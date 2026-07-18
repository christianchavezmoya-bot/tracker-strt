"""
HOLO-RTLS — User Model
Email/password auth + TOTP 2FA + role-based access control.
"""
from datetime import datetime, timezone
from enum import IntEnum
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from backend.extensions import db
from backend.config import (
    ARGON2_MEMORY_COST, ARGON2_TIME_COST, ARGON2_PARALLELISM,
    LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_SECONDS
)

# ── Hasher ───────────────────────────────────────────────────────────────────
_ph = PasswordHasher(
    memory_cost=ARGON2_MEMORY_COST,
    time_cost=ARGON2_TIME_COST,
    parallelism=ARGON2_PARALLELISM,
)


# ── Enums ────────────────────────────────────────────────────────────────────
class UserRole(IntEnum):
    VIEWER = 1      # Read-only access
    OPERATOR = 2    # Can manage trackers + acknowledge alerts
    ADMIN = 3       # Full access


# ── Model ────────────────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username      = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role          = db.Column(db.Integer, nullable=False, default=UserRole.VIEWER)
    display_name  = db.Column(db.String(200))
    is_active     = db.Column(db.Boolean, default=True)
    is_2fa_enabled = db.Column(db.Boolean, default=False)
    # TOTP secret stored encrypted at rest (in production: encrypt this field)
    totp_secret   = db.Column(db.String(64), nullable=True)
    # Login security
    failed_attempts = db.Column(db.Integer, default=0)
    locked_until    = db.Column(db.DateTime, nullable=True)
    # Audit
    last_login    = db.Column(db.DateTime, nullable=True)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    notifications = db.relationship("Notification", back_populates="user", lazy="dynamic",
                                     cascade="all, delete-orphan")
    audit_logs    = db.relationship("AuditLog", back_populates="user", lazy="dynamic",
                                     cascade="all, delete-orphan")
    api_keys      = db.relationship("ApiKey", back_populates="user", lazy="dynamic",
                                   cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email} [{self.role.name}]>"

    # ── Password ──────────────────────────────────────────────────────────────
    def set_password(self, plain_password: str) -> None:
        """Hash and store the password using Argon2."""
        self.password_hash = _ph.hash(plain_password)

    def check_password(self, plain_password: str) -> bool:
        """Verify password. Returns True on success, False otherwise."""
        try:
            _ph.verify(self.password_hash, plain_password)
            return True
        except (VerifyMismatchError, InvalidHash):
            return False

    # ── Login lockout ────────────────────────────────────────────────────────
    def record_failed_login(self) -> bool:
        """
        Record a failed attempt. Returns True if the account is now locked.
        """
        self.failed_attempts += 1
        if self.failed_attempts >= LOGIN_MAX_ATTEMPTS:
            from datetime import timedelta
            self.locked_until = datetime.now(timezone.utc) + timedelta(seconds=LOGIN_LOCKOUT_SECONDS)
            db.session.commit()
            return True
        db.session.commit()
        return False

    def record_successful_login(self) -> None:
        """Reset failed attempts and update last login."""
        self.failed_attempts = 0
        self.locked_until = None
        self.last_login = datetime.now(timezone.utc)
        db.session.commit()

    @property
    def is_locked(self) -> bool:
        """True if the account is currently locked due to failed attempts."""
        if self.locked_until is None:
            return False
        return datetime.now(timezone.utc) < self.locked_until

    # ── Permissions ──────────────────────────────────────────────────────────
    @property
    def role_name(self) -> str:
        return self.role.name

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission (by role)."""
        from backend.services.rbac_service import RBAC_SERVICE
        return RBAC_SERVICE.user_has_permission(self, permission)

    def to_dict(self, include_email: bool = False) -> dict:
        """Public-safe user dict."""
        data = {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role_name,
            "is_active": self.is_active,
            "is_2fa_enabled": self.is_2fa_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }
        if include_email:
            data["email"] = self.email
        return data
