"""
HOLO-RTLS — Audit Log Model
Immutable append-only audit trail.
"""
from datetime import datetime, timezone
from backend.extensions import db


class AuditLog(db.Model):
    """
    Immutable audit trail. Rows should never be updated or deleted.
    Logged by the audit_service on every write operation.
    """
    __tablename__ = "audit_logs"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    # user_id is nullable for system-initiated events (e.g., scheduler, MQTT ingest)
    action      = db.Column(db.String(100), nullable=False, index=True)
    # action examples: user.login, user.logout, tracker.create, alert.acknowledge, settings.update
    entity_type = db.Column(db.String(50), nullable=True, index=True)
    # entity_type examples: User, Tracker, Alert, Zone, WifiNode, BusinessSetting
    entity_id   = db.Column(db.Integer, nullable=True)
    details     = db.Column(db.Text, nullable=True)   # JSON with relevant before/after values
    ip_address  = db.Column(db.String(45), nullable=True)   # IPv6 compatible
    user_agent  = db.Column(db.String(500), nullable=True)
    timestamp   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                            nullable=False, index=True)

    user = db.relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.action} {self.entity_type}:{self.entity_id} at {self.timestamp}>"

    @classmethod
    def log(cls, action: str, user_id=None, entity_type: str = None,
            entity_id: int = None, details: str = None, ip_address: str = None,
            user_agent: str = None):
        """Factory method — creates and commits an audit entry."""
        entry = cls(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.session.add(entry)
        db.session.commit()
        return entry

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.display_name if self.user else "System",
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
