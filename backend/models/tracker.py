"""
HOLO-RTLS — Tracker, WifiNode, and MapSection Models
"""
from datetime import datetime, timezone
from enum import IntEnum
from backend.extensions import db


# ── Enums ────────────────────────────────────────────────────────────────────
class DeviceCategory(IntEnum):
    PERSONNEL_TAG = 1
    MACHINE_TAG   = 2
    SMARTPHONE    = 3
    SMARTWATCH    = 4
    ENV_SENSOR    = 5
    UWB_ANCHOR    = 6


class TagType(IntEnum):
    PERSONNEL = 1
    MACHINE   = 2


class AssetState(IntEnum):
    ACTIVE        = 1
    OFFLINE       = 2
    MAINTENANCE   = 3
    DECOMMISSIONED = 4


class AlertStatus(IntEnum):
    NORMAL           = 0
    NO_MOVEMENT      = 1
    NO_SIGNAL        = 2
    RESTRICTED_ZONE  = 3
    LOW_BATTERY      = 4
    CRITICAL_VITALS  = 5
    ENV_HAZARD       = 6


class CheckInStatus(IntEnum):
    UNCHECKED   = 0
    CHECKED_IN  = 1
    CHECKED_OUT = 2


# ── Tracker (Tag) Model ───────────────────────────────────────────────────────
class Tracker(db.Model):
    __tablename__ = "trackers"

    id            = db.Column(db.Integer, primary_key=True)
    hardware_id   = db.Column(db.String(100), unique=True, nullable=False, index=True)
    assigned_name = db.Column(db.String(200), nullable=True)
    tag_type      = db.Column(db.Integer, nullable=False, default=TagType.PERSONNEL)
    category      = db.Column(db.Integer, nullable=False, default=DeviceCategory.PERSONNEL_TAG)
    icon_index    = db.Column(db.Integer, default=0)
    asset_state   = db.Column(db.Integer, nullable=False, default=AssetState.ACTIVE)
    # Position (updated by positioning engine)
    pos_x         = db.Column(db.Float, default=0.0)
    pos_y         = db.Column(db.Float, default=0.0)
    pos_z         = db.Column(db.Float, default=0.0)
    level_or_z    = db.Column(db.Integer, default=0)
    # Live telemetry
    battery_level = db.Column(db.Float, default=100.0)
    heart_rate    = db.Column(db.Float, nullable=True)
    sp_o2         = db.Column(db.Float, nullable=True)
    temperature   = db.Column(db.Float, nullable=True)
    gas_ppm       = db.Column(db.Float, nullable=True)
    # Alert state
    alert_status  = db.Column(db.Integer, default=AlertStatus.NORMAL)
    # Tracking
    last_report_time    = db.Column(db.Float, nullable=True)   # Unix timestamp
    last_movement_time  = db.Column(db.Float, nullable=True)
    check_status        = db.Column(db.Integer, default=CheckInStatus.UNCHECKED)
    current_section_name = db.Column(db.String(200), nullable=True)
    # Metadata
    metadata_json = db.Column(db.Text, nullable=True)   # Free-form extra data
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    history       = db.relationship("TrackingHistory", back_populates="tracker",
                                   lazy="dynamic", cascade="all, delete-orphan")
    alerts        = db.relationship("Alert", back_populates="tracker",
                                   lazy="dynamic", cascade="all, delete-orphan")
    check_in_logs = db.relationship("CheckInLog", back_populates="tracker",
                                   lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Tracker {self.hardware_id} [{self.assigned_name or 'unnamed'}]>"

    @property
    def category_name(self) -> str:
        try:
            return DeviceCategory(self.category).name
        except ValueError:
            return "UNKNOWN"

    @property
    def asset_state_name(self) -> str:
        try:
            return AssetState(self.asset_state).name
        except ValueError:
            return "UNKNOWN"

    @property
    def alert_status_name(self) -> str:
        try:
            return AlertStatus(self.alert_status).name
        except ValueError:
            return "NORMAL"

    @property
    def is_online(self) -> bool:
        return self.alert_status != AlertStatus.NO_SIGNAL and self.asset_state == AssetState.ACTIVE

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "hardware_id": self.hardware_id,
            "assigned_name": self.assigned_name,
            "tag_type": TagType(self.tag_type).name,
            "category": self.category_name,
            "asset_state": self.asset_state_name,
            "position": {"x": self.pos_x, "y": self.pos_y, "z": self.pos_z},
            "battery_level": self.battery_level,
            "heart_rate": self.heart_rate,
            "sp_o2": self.sp_o2,
            "temperature": self.temperature,
            "gas_ppm": self.gas_ppm,
            "alert_status": self.alert_status_name,
            "last_report_time": self.last_report_time,
            "current_section": self.current_section_name,
            "check_status": CheckInStatus(self.check_status).name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── WiFi / BLE Node (Fixed Anchor) Model ─────────────────────────────────────
class NodeType(IntEnum):
    STANDARD = 1
    CHECK_IN  = 2
    CHECK_OUT = 3


class NodeStatus(IntEnum):
    ACTIVE      = 1
    CALIBRATING = 2
    OFFLINE     = 3


class WifiNode(db.Model):
    __tablename__ = "wifi_nodes"

    id            = db.Column(db.Integer, primary_key=True)
    mac_address    = db.Column(db.String(50), unique=True, nullable=False, index=True)
    assigned_name = db.Column(db.String(200), nullable=True)
    pos_x         = db.Column(db.Float, default=0.0)
    pos_y         = db.Column(db.Float, default=0.0)
    pos_z         = db.Column(db.Float, default=0.0)
    node_type     = db.Column(db.Integer, default=NodeType.STANDARD)
    status        = db.Column(db.Integer, default=NodeStatus.ACTIVE)
    last_heartbeat = db.Column(db.DateTime, nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    check_in_logs = db.relationship("CheckInLog", back_populates="node", lazy="dynamic")

    def __repr__(self):
        return f"<WifiNode {self.mac_address} [{self.assigned_name}]>"

    @property
    def node_type_name(self) -> str:
        try:
            return NodeType(self.node_type).name
        except ValueError:
            return "STANDARD"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mac_address": self.mac_address,
            "assigned_name": self.assigned_name,
            "position": {"x": self.pos_x, "y": self.pos_y, "z": self.pos_z},
            "node_type": self.node_type_name,
            "status": NodeStatus(self.status).name,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
        }


# ── Map Section (Polygon Area) Model ──────────────────────────────────────────
class MapSection(db.Model):
    __tablename__ = "map_sections"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(200), nullable=False)
    polygon_json  = db.Column(db.Text, nullable=False)   # JSON: [[x,y], [x,y], ...]
    is_restricted = db.Column(db.Boolean, default=False)
    is_visible    = db.Column(db.Boolean, default=True)
    color_hex     = db.Column(db.String(8), default="#00e5ff")
    z_index       = db.Column(db.Integer, default=0)     # For multi-floor ordering
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    zones = db.relationship("Zone", back_populates="section", lazy="dynamic",
                            cascade="all, delete-orphan")

    def __repr__(self):
        return f"<MapSection {self.name} restricted={self.is_restricted}>"

    def get_polygon_points(self):
        import json
        return json.loads(self.polygon_json)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "polygon": self.get_polygon_points(),
            "is_restricted": self.is_restricted,
            "is_visible": self.is_visible,
            "color_hex": self.color_hex,
            "z_index": self.z_index,
            "image_url": getattr(self, 'image_url', None) or None,
        }


# ── Zone (Sphere / Restricted Area) Model ─────────────────────────────────────
class ZoneType(IntEnum):
    NORMAL      = 1
    RESTRICTED  = 2
    CHECK_IN    = 3
    CHECK_OUT   = 4
    DANGER      = 5


class Zone(db.Model):
    __tablename__ = "zones"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(200), nullable=False)
    zone_type     = db.Column(db.Integer, nullable=False, default=ZoneType.NORMAL)
    pos_x         = db.Column(db.Float, default=0.0)
    pos_y         = db.Column(db.Float, default=0.0)
    pos_z         = db.Column(db.Float, default=0.0)
    radius        = db.Column(db.Float, default=5.0)    # meters
    is_visible    = db.Column(db.Boolean, default=True)
    color_hex     = db.Column(db.String(8), default="#00e5ff")
    section_id    = db.Column(db.Integer, db.ForeignKey("map_sections.id"), nullable=True)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    section = db.relationship("MapSection", back_populates="zones")

    def __repr__(self):
        return f"<Zone {self.name} [{ZoneType(self.zone_type).name}]>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "zone_type": ZoneType(self.zone_type).name,
            "position": {"x": self.pos_x, "y": self.pos_y, "z": self.pos_z},
            "radius": self.radius,
            "is_visible": self.is_visible,
            "color_hex": self.color_hex,
            "section_id": self.section_id,
        }
