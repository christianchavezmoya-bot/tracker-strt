"""
HOLO-RTLS — Tracking History Model
Stores position history for all trackers. Used by history playback and reports.
"""
from datetime import datetime, timezone
from backend.extensions import db


class TrackingHistory(db.Model):
    """
    Stores each position measurement. Pruned automatically by the history service.
    """
    __tablename__ = "tracking_history"

    id = db.Column(db.Integer, primary_key=True)
    tracker_id = db.Column(db.Integer, db.ForeignKey("trackers.id"), nullable=False, index=True)
    x = db.Column(db.Float, nullable=False)          # real-world X in meters
    y = db.Column(db.Float, nullable=False)          # real-world Y in meters
    z = db.Column(db.Float, default=0.0)              # real-world Z in meters (floor height)
    accuracy = db.Column(db.Float, nullable=True)    # estimated RMSE in meters
    hardware_id = db.Column(db.String(64), nullable=True)  # source hardware identifier
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Optional: velocity / heading (computed from consecutive positions)
    vx = db.Column(db.Float, nullable=True)
    vy = db.Column(db.Float, nullable=True)
    speed = db.Column(db.Float, nullable=True)        # m/s

    __table_args__ = (
        db.Index("ix_tracking_history_tracker_timestamp", "tracker_id", "timestamp"),
    )

    tracker = db.relationship("Tracker", back_populates="history")

    def to_dict(self):
        return {
            "id": self.id,
            "tracker_id": self.tracker_id,
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "z": round(self.z, 3),
            "accuracy": round(self.accuracy, 3) if self.accuracy else None,
            "hardware_id": self.hardware_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "vx": round(self.vx, 3) if self.vx else None,
            "vy": round(self.vy, 3) if self.vy else None,
            "speed": round(self.speed, 3) if self.speed else None,
        }


class PositionSnapshot(db.Model):
    """
    Current (latest) position of every tracker. Single row per tracker.
    Written by the ingestion loop on every update.
    """
    __tablename__ = "position_snapshot"

    tracker_id = db.Column(db.Integer, db.ForeignKey("trackers.id"), primary_key=True)
    x = db.Column(db.Float, nullable=False)
    y = db.Column(db.Float, nullable=False)
    z = db.Column(db.Float, default=0.0)
    accuracy = db.Column(db.Float, nullable=True)
    vx = db.Column(db.Float, nullable=True)
    vy = db.Column(db.Float, nullable=True)
    speed = db.Column(db.Float, nullable=True)
    source = db.Column(db.String(32), nullable=True)   # "UWB", "BLE", "WiFi", "MOCK"
    hardware_id = db.Column(db.String(64), nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen_hardware = db.Column(db.DateTime, nullable=True)  # when hardware last reported

    def to_dict(self):
        return {
            "tracker_id": self.tracker_id,
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "z": round(self.z, 3),
            "accuracy": round(self.accuracy, 3) if self.accuracy else None,
            "vx": round(self.vx, 3) if self.vx else None,
            "vy": round(self.vy, 3) if self.vy else None,
            "speed": round(self.speed, 3) if self.speed else None,
            "source": self.source,
            "hardware_id": self.hardware_id,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_seen_hardware": self.last_seen_hardware.isoformat() if self.last_seen_hardware else None,
        }


class TrackerPresenceLog(db.Model):
    """Online/offline + RSSI samples for tracker timeline charts."""
    __tablename__ = "tracker_presence_log"

    id = db.Column(db.Integer, primary_key=True)
    tracker_id = db.Column(db.Integer, db.ForeignKey("trackers.id"), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    online = db.Column(db.Boolean, default=True, nullable=False)
    rssi = db.Column(db.Float, nullable=True)

    __table_args__ = (
        db.Index("ix_presence_tracker_ts", "tracker_id", "timestamp"),
    )

    tracker = db.relationship("Tracker", backref=db.backref("presence_logs", lazy="dynamic"))

    def to_dict(self):
        return {
            "tracker_id": self.tracker_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "online": bool(self.online),
            "rssi": self.rssi,
        }


class NodePresenceLog(db.Model):
    """MQTT heartbeat / online samples for anchor timeline charts."""
    __tablename__ = "node_presence_log"

    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.Integer, db.ForeignKey("wifi_nodes.id"), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    online = db.Column(db.Boolean, default=True, nullable=False)
    rssi = db.Column(db.Float, nullable=True)
    node_ip = db.Column(db.String(64), nullable=True)

    __table_args__ = (
        db.Index("ix_node_presence_ts", "node_id", "timestamp"),
    )

    node = db.relationship("WifiNode", backref=db.backref("presence_logs", lazy="dynamic"))

    def to_dict(self):
        return {
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "online": bool(self.online),
            "rssi": self.rssi,
            "node_ip": self.node_ip,
        }
