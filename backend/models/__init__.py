"""
HOLO-RTLS — All Models
Import this module to load all SQLAlchemy models.
"""
from backend.models.user import User, UserRole
from backend.models.tracker import (
    Tracker, WifiNode, MapSection, Zone,
    DeviceCategory, TagType, AssetState, AlertStatus,
    CheckInStatus, NodeType, NodeStatus, ZoneType,
)
from backend.models.alert import Alert, Notification, AlertType, AlertState, NotificationType
from backend.models.audit import AuditLog
from backend.models.settings import Setting, BusinessLogo, SettingScope
from backend.models.backup import BackupJob, CheckInLog, ApiKey
from backend.models.hardware import HardwareConfig, HardwareType, Protocol, ConnectionStatus
from backend.models.positioning import TrackingHistory, PositionSnapshot
from backend.models.detection import (
    FloorPlan, WifiAnchor, DetectionEvent, TrackedDevice,
    SignalType, AnchorStatus, DeviceType,
)

__all__ = [
    # User
    "User", "UserRole",
    # Tracker
    "Tracker", "WifiNode", "MapSection", "Zone",
    "DeviceCategory", "TagType", "AssetState", "AlertStatus",
    "CheckInStatus", "NodeType", "NodeStatus", "ZoneType",
    # Alert
    "Alert", "Notification", "AlertType", "AlertState", "NotificationType",
    # Audit
    "AuditLog",
    # Settings
    "Setting", "BusinessLogo", "SettingScope",
    # Backup / History / API
    "BackupJob", "CheckInLog", "ApiKey",
    # Positioning
    "TrackingHistory", "PositionSnapshot",
    # Hardware
    "HardwareConfig",
    # WiFi/BLE RTLS
    "FloorPlan", "WifiAnchor", "DetectionEvent", "TrackedDevice",
    "SignalType", "AnchorStatus", "DeviceType",
]
