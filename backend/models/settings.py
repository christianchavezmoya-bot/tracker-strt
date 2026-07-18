"""
HOLO-RTLS — Settings Models
Key-value business + system configuration store.
"""
from datetime import datetime, timezone
from enum import IntEnum
from backend.extensions import db


class SettingScope(IntEnum):
    SYSTEM   = 1   # System-wide settings
    BUSINESS = 2   # Business/facility settings
    ALERT    = 3   # Alert threshold settings


# ── Business / System Settings Store ────────────────────────────────────────
class Setting(db.Model):
    """
    Generic key-value store for all settings.
    Admin creates/edits via the Settings API.
    """
    __tablename__ = "settings"

    id        = db.Column(db.Integer, primary_key=True)
    scope     = db.Column(db.Integer, nullable=False, default=SettingScope.BUSINESS)
    key       = db.Column(db.String(100), nullable=False, unique=True, index=True)
    value     = db.Column(db.Text, nullable=True)
    value_type = db.Column(db.String(20), default="string")   # string, int, float, bool, json
    label     = db.Column(db.String(200), nullable=True)     # Human-readable label
    description = db.Column(db.String(500), nullable=True)  # Help text
    is_secret  = db.Column(db.Boolean, default=False)        # Mask in UI if true
    is_readonly = db.Column(db.Boolean, default=False)       # System-protected setting
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def __repr__(self):
        return f"<Setting {self.key}={self.value}>"

    def get_typed_value(self):
        """Return value cast to its declared type."""
        if self.value is None:
            return None
        if self.value_type == "int":
            return int(self.value)
        if self.value_type == "float":
            return float(self.value)
        if self.value_type == "bool":
            return self.value.lower() in ("true", "1", "yes")
        if self.value_type == "json":
            import json
            return json.loads(self.value)
        return self.value

    def set_typed_value(self, value) -> None:
        """Store value as string, tracking the type."""
        if isinstance(value, bool):
            self.value = "true" if value else "false"
            self.value_type = "bool"
        elif isinstance(value, int):
            self.value = str(value)
            self.value_type = "int"
        elif isinstance(value, float):
            self.value = str(value)
            self.value_type = "float"
        elif isinstance(value, dict) or isinstance(value, list):
            import json
            self.value = json.dumps(value)
            self.value_type = "json"
        else:
            self.value = str(value)
            self.value_type = "string"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scope": SettingScope(self.scope).name,
            "key": self.key,
            "value": "********" if self.is_secret else self.value,
            "value_type": self.value_type,
            "label": self.label,
            "description": self.description,
            "is_secret": self.is_secret,
            "is_readonly": self.is_readonly,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ── Business Logo ────────────────────────────────────────────────────────────
class BusinessLogo(db.Model):
    """
    Stores the current business/facility logo.
    Single row — always update, never create new rows.
    """
    __tablename__ = "business_logos"

    id         = db.Column(db.Integer, primary_key=True)
    filename   = db.Column(db.String(255), nullable=False)   # Stored filename in uploads/
    original_name = db.Column(db.String(255), nullable=False)
    mime_type  = db.Column(db.String(50), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "original_name": self.original_name,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }
