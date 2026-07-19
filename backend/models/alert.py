"""
HOLO-RTLS — Alert and Notification Models
"""
from datetime import datetime, timezone
from enum import IntEnum
from backend.extensions import db


class AlertType(IntEnum):
    NO_SIGNAL        = 1
    NO_MOVEMENT      = 2
    RESTRICTED_ZONE  = 3
    LOW_BATTERY      = 4
    CRITICAL_VITALS  = 5
    ENV_HAZARD       = 6
    NODE_OFFLINE     = 7
    MANUAL           = 8
    PROXIMITY        = 9


class AlertState(IntEnum):
    ACTIVE       = 1
    ACKNOWLEDGED = 2
    RESOLVED     = 3
    ESCALATED    = 4


class NotificationType(IntEnum):
    ALERT      = 1   # In-app alert notification
    SYSTEM     = 2   # System-wide info
    REPORT     = 3   # Report ready / delivered
    SECURITY   = 4   # Login events, etc.
    DOWNLINK   = 5   # Downlink command acknowledgement


# ── Alert Model ───────────────────────────────────────────────────────────────
class Alert(db.Model):
    __tablename__ = "alerts"

    id              = db.Column(db.Integer, primary_key=True)
    tracker_id      = db.Column(db.Integer, db.ForeignKey("trackers.id"), nullable=True)
    node_id         = db.Column(db.Integer, db.ForeignKey("wifi_nodes.id"), nullable=True)
    alert_type      = db.Column(db.Integer, nullable=False)
    state           = db.Column(db.Integer, nullable=False, default=AlertState.ACTIVE)
    message         = db.Column(db.String(500), nullable=True)
    # Position at time of alert (for history playback)
    pos_x           = db.Column(db.Float, nullable=True)
    pos_y           = db.Column(db.Float, nullable=True)
    pos_z           = db.Column(db.Float, nullable=True)
    section_name    = db.Column(db.String(200), nullable=True)
    # Acknowledgement
    acknowledged_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    acknowledged_at    = db.Column(db.DateTime, nullable=True)
    acknowledgement_notes = db.Column(db.String(500), nullable=True)
    # Escalation
    escalated_at    = db.Column(db.DateTime, nullable=True)
    escalated_to    = db.Column(db.String(500), nullable=True)   # Email/SMS targets
    # Timestamps
    triggered_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                nullable=False)
    resolved_at     = db.Column(db.DateTime, nullable=True)
    updated_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    tracker         = db.relationship("Tracker", back_populates="alerts")
    acknowledged_by = db.relationship("User", foreign_keys=[acknowledged_by_id])

    def __repr__(self):
        return f"<Alert {AlertType(self.alert_type).name} tracker={self.tracker_id} [{AlertState(self.state).name}]>"

    @property
    def alert_type_name(self) -> str:
        try:
            return AlertType(self.alert_type).name
        except ValueError:
            return "UNKNOWN"

    @property
    def state_name(self) -> str:
        try:
            return AlertState(self.state).name
        except ValueError:
            return "UNKNOWN"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tracker_id": self.tracker_id,
            "node_id": self.node_id,
            "alert_type": self.alert_type_name,
            "state": self.state_name,
            "message": self.message,
            "position": {"x": self.pos_x, "y": self.pos_y, "z": self.pos_z},
            "section_name": self.section_name,
            "acknowledged_by": self.acknowledged_by.display_name if self.acknowledged_by else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledgement_notes": self.acknowledgement_notes,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


# ── Notification Model (in-app) ───────────────────────────────────────────────
class Notification(db.Model):
    __tablename__ = "notifications"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    type       = db.Column(db.Integer, nullable=False, default=NotificationType.ALERT)
    title      = db.Column(db.String(200), nullable=False)
    message    = db.Column(db.String(500), nullable=True)
    is_read    = db.Column(db.Boolean, default=False)
    link_url   = db.Column(db.String(500), nullable=True)   # Deep link to the relevant entity
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="notifications")

    def __repr__(self):
        return f"<Notification {self.id} for user={self.user_id} read={self.is_read}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": NotificationType(self.type).name,
            "title": self.title,
            "message": self.message,
            "is_read": self.is_read,
            "link_url": self.link_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
