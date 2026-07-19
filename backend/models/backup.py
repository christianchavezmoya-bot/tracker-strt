"""
HOLO-RTLS — Backup, History, and ApiKey Models
"""
from datetime import datetime, timezone
from enum import IntEnum
from backend.extensions import db


# ── Backup Job Model ──────────────────────────────────────────────────────────
class BackupJob(db.Model):
    __tablename__ = "backup_jobs"

    id          = db.Column(db.Integer, primary_key=True)
    filename    = db.Column(db.String(255), nullable=False)
    size_bytes  = db.Column(db.Integer, nullable=True)
    status      = db.Column(db.String(20), default="pending")   # pending / running / done / failed
    trigger     = db.Column(db.String(20), default="manual")    # manual / scheduled
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    notes       = db.Column(db.String(500), nullable=True)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<BackupJob {self.id} {self.filename} [{self.status}]>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "status": self.status,
            "trigger": self.trigger,
            "created_by": self.created_by_id,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }



# ── Check-In / Check-Out Log ─────────────────────────────────────────────────
class CheckInLog(db.Model):
    __tablename__ = "check_in_logs"

    id          = db.Column(db.Integer, primary_key=True)
    tracker_id  = db.Column(db.Integer, db.ForeignKey("trackers.id"), nullable=False)
    node_id     = db.Column(db.Integer, db.ForeignKey("wifi_nodes.id"), nullable=False)
    direction   = db.Column(db.String(10), nullable=False)   # "check_in" or "check_out"
    timestamp   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tracker = db.relationship("Tracker", back_populates="check_in_logs")
    node    = db.relationship("WifiNode", back_populates="check_in_logs")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tracker_id": self.tracker_id,
            "node_id": self.node_id,
            "direction": self.direction,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ── API Key Model ────────────────────────────────────────────────────────────
class ApiKey(db.Model):
    """
    Long-lived API keys for external integrations.
    Hash stored, not the raw key (users get the raw key once on creation).
    """
    __tablename__ = "api_keys"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name         = db.Column(db.String(100), nullable=False)
    key_prefix   = db.Column(db.String(20), nullable=False)   # First 8 chars shown in UI
    key_hash     = db.Column(db.String(255), nullable=False)
    permissions  = db.Column(db.Text, nullable=True)          # JSON list of permission strings
    last_used_at = db.Column(db.DateTime, nullable=True)
    expires_at   = db.Column(db.DateTime, nullable=True)
    is_active    = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="api_keys")

    def __repr__(self):
        return f"<ApiKey {self.name} [{self.key_prefix}****]>"

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "permissions": self.permissions,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
