"""
HOLO-RTLS — Detection / Scanner / Floor Plan Models
Supports WiFi + BLE RSSI-based RTLS via trilateration.
"""
from datetime import datetime
from enum import IntEnum
from backend.extensions import db


def _utcnow():
    return datetime.utcnow()


# ── Signal Types ──────────────────────────────────────────────────────────────
class SignalType(IntEnum):
    WIFI  = 1
    BLE   = 2


# ── Floor Plan ───────────────────────────────────────────────────────────────
class FloorPlan(db.Model):
    __tablename__ = "floor_plans"

    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(200), nullable=False)
    level            = db.Column(db.Integer, default=0)
    image_url        = db.Column(db.String(500), nullable=True)
    real_width       = db.Column(db.Float, nullable=True)    # metres
    real_height      = db.Column(db.Float, nullable=True)    # metres
    # Affine: {a,b,c,d,e,f} maps pixel → real-world metres
    calibration_json = db.Column(db.Text, nullable=True)
    is_active        = db.Column(db.Boolean, default=True)
    created_at       = db.Column(db.DateTime, default=_utcnow)
    updated_at       = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    anchors = db.relationship("WifiAnchor", back_populates="floor_plan",
                            lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<FloorPlan {self.name} [L{self.level}]>"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "image_url": self.image_url,
            "real_width": self.real_width,
            "real_height": self.real_height,
            "calibration": self._parse_calibration(),
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def _parse_calibration(self):
        import json
        if self.calibration_json:
            try:
                return json.loads(self.calibration_json)
            except Exception:
                return None
        return None


# ── WiFi / BLE Anchor (Fixed Scanner Node) ──────────────────────────────────
class AnchorStatus(IntEnum):
    ACTIVE      = 1
    CALIBRATING = 2
    OFFLINE     = 3


class WifiAnchor(db.Model):
    __tablename__ = "wifi_anchors"

    id            = db.Column(db.Integer, primary_key=True)
    mac_address   = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name          = db.Column(db.String(200), nullable=True)
    # Pixel position on floor plan canvas
    pixel_x       = db.Column(db.Float, nullable=True)
    pixel_y       = db.Column(db.Float, nullable=True)
    # Calibrated real-world position (metres)
    real_x        = db.Column(db.Float, nullable=True)
    real_y        = db.Column(db.Float, nullable=True)
    real_z        = db.Column(db.Float, default=0.0)
    floor_plan_id = db.Column(db.Integer, db.ForeignKey("floor_plans.id"), nullable=True)
    status        = db.Column(db.Integer, default=AnchorStatus.ACTIVE)
    tx_power      = db.Column(db.Float, default=-40.0)   # dBm at 1m
    avg_rssi      = db.Column(db.Float, nullable=True)
    last_seen     = db.Column(db.DateTime, nullable=True)
    created_at    = db.Column(db.DateTime, default=_utcnow)
    updated_at    = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    floor_plan  = db.relationship("FloorPlan", back_populates="anchors")
    detections   = db.relationship("DetectionEvent", back_populates="anchor", lazy="dynamic")

    def __repr__(self):
        return f"<WifiAnchor {self.mac_address} [{self.name or 'unnamed'}]>"

    @property
    def status_name(self) -> str:
        try:
            return AnchorStatus(self.status).name
        except ValueError:
            return "UNKNOWN"

    def to_dict(self):
        return {
            "id": self.id,
            "mac_address": self.mac_address,
            "name": self.name,
            "pixel_x": self.pixel_x,
            "pixel_y": self.pixel_y,
            "real_x": self.real_x,
            "real_y": self.real_y,
            "real_z": self.real_z,
            "floor_plan_id": self.floor_plan_id,
            "status": self.status_name,
            "tx_power": self.tx_power,
            "avg_rssi": self.avg_rssi,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


# ── Detection Event (raw RSSI reading) ─────────────────────────────────────
class DetectionEvent(db.Model):
    __tablename__ = "detection_events"

    id           = db.Column(db.Integer, primary_key=True)
    anchor_id    = db.Column(db.Integer, db.ForeignKey("wifi_anchors.id"), nullable=False, index=True)
    mac_address  = db.Column(db.String(50), nullable=False, index=True)
    rssi         = db.Column(db.Float, nullable=False)          # dBm
    signal_type  = db.Column(db.Integer, nullable=False)       # SignalType.WIFI / .BLE
    ssid         = db.Column(db.String(200), nullable=True)   # WiFi SSID
    adv_name     = db.Column(db.String(200), nullable=True)   # BLE advertised name
    channel      = db.Column(db.Integer, nullable=True)        # WiFi channel
    timestamp    = db.Column(db.DateTime, default=_utcnow, index=True)

    anchor = db.relationship("WifiAnchor", back_populates="detections")

    __table_args__ = (
        db.Index("ix_detection_mac_timestamp", "mac_address", "timestamp"),
        db.Index("ix_detection_anchor_timestamp", "anchor_id", "timestamp"),
    )

    def __repr__(self):
        return f"<DetectionEvent {self.mac_address} RSSI={self.rssi} anchor={self.anchor_id}>"

    @property
    def signal_type_name(self) -> str:
        try:
            return SignalType(self.signal_type).name
        except ValueError:
            return "UNKNOWN"

    def to_dict(self):
        return {
            "id": self.id,
            "anchor_id": self.anchor_id,
            "mac_address": self.mac_address,
            "rssi": self.rssi,
            "signal_type": self.signal_type_name,
            "ssid": self.ssid,
            "adv_name": self.adv_name,
            "channel": self.channel,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ── Tracked Device ───────────────────────────────────────────────────────────
class DeviceType(IntEnum):
    UNKNOWN       = 0
    SMARTPHONE   = 1
    LAPTOP       = 2
    TABLET       = 3
    IOT_DEVICE   = 4
    PERSONNEL_TAG = 5
    OTHER        = 99


class TrackedDevice(db.Model):
    __tablename__ = "tracked_devices"

    id            = db.Column(db.Integer, primary_key=True)
    mac_address  = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name         = db.Column(db.String(200), nullable=True)
    device_type  = db.Column(db.Integer, default=DeviceType.UNKNOWN)
    pos_x        = db.Column(db.Float, nullable=True)
    pos_y        = db.Column(db.Float, nullable=True)
    pos_z        = db.Column(db.Float, default=0.0)
    pos_accuracy = db.Column(db.Float, nullable=True)   # metres
    pos_source   = db.Column(db.String(16), nullable=True)  # "TRILATERATION"
    first_seen   = db.Column(db.DateTime, default=_utcnow)
    last_seen    = db.Column(db.DateTime, default=_utcnow)
    is_active    = db.Column(db.Boolean, default=True)
    notes        = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<TrackedDevice {self.mac_address} [{self.name or 'unnamed'}]>"

    @property
    def device_type_name(self) -> str:
        try:
            return DeviceType(self.device_type).name
        except ValueError:
            return "UNKNOWN"

    def to_dict(self):
        return {
            "id": self.id,
            "mac_address": self.mac_address,
            "name": self.name,
            "device_type": self.device_type_name,
            "position": {"x": self.pos_x, "y": self.pos_y, "z": self.pos_z}
                        if self.pos_x is not None else None,
            "pos_accuracy": self.pos_accuracy,
            "pos_source": self.pos_source,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "is_active": self.is_active,
            "notes": self.notes,
        }
