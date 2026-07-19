"""
HOLO-RTLS — Hardware Configuration Model
Stores connection settings for real hardware (UWB, BLE, WiFi).
"""
from datetime import datetime, timezone
from enum import IntEnum
from backend.extensions import db


class HardwareType(IntEnum):
    UWB      = 1
    BLE      = 2
    WIFI     = 3
    ENVIRO   = 4   # Environmental sensors


class Protocol(IntEnum):
    MQTT       = 1
    SERIAL     = 2
    REST       = 3
    WEBSOCKET  = 4
    BLE_GATT   = 5
    HTTP_POLL  = 6
    I2C        = 7


class ConnectionStatus(IntEnum):
    DISCONNECTED  = 0
    CONNECTING    = 1
    CONNECTED     = 2
    ERROR         = 3


class HardwareConfig(db.Model):
    """
    Per-device configuration entry.
    Multiple configs can be active simultaneously.
    """
    __tablename__ = "hardware_configs"

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100), nullable=False)
    hardware_type   = db.Column(db.Integer, nullable=False)   # HardwareType enum
    protocol        = db.Column(db.Integer, nullable=False)   # Protocol enum
    # Profile ID — maps to backend/models/hardware_profiles.py profiles
    profile_id      = db.Column(db.String(50), nullable=True)
    # Connection settings (stored as JSON)
    settings_json   = db.Column(db.Text, nullable=True)      # Protocol-specific settings
    # Status
    status          = db.Column(db.Integer, default=ConnectionStatus.DISCONNECTED)
    last_seen       = db.Column(db.DateTime, nullable=True)
    error_message    = db.Column(db.String(500), nullable=True)
    # Live data toggle
    is_active       = db.Column(db.Boolean, default=True)
    # Metadata
    notes           = db.Column(db.Text, nullable=True)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                onupdate=lambda: datetime.now(timezone.utc))
    created_by_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def __repr__(self):
        return f"<HardwareConfig {self.name} [{HardwareType(self.hardware_type).name}]>"

    @property
    def hardware_type_name(self):
        try:
            return HardwareType(self.hardware_type).name
        except ValueError:
            return "UNKNOWN"

    @property
    def protocol_name(self):
        try:
            return Protocol(self.protocol).name
        except ValueError:
            return "UNKNOWN"

    @property
    def status_name(self):
        try:
            return ConnectionStatus(self.status).name
        except ValueError:
            return "UNKNOWN"

    def get_settings(self) -> dict:
        import json
        if not self.settings_json:
            return {}
        try:
            return json.loads(self.settings_json)
        except Exception:
            return {}

    def set_settings(self, settings: dict) -> None:
        import json
        self.settings_json = json.dumps(settings)

    def to_dict(self, include_sensitive: bool = False) -> dict:
        settings = self.get_settings()
        if not include_sensitive:
            # Mask passwords and tokens in API response
            for key in settings:
                if any(s in key.lower() for s in ("password", "token", "secret", "key")):
                    settings[key] = "********"
        return {
            "id": self.id,
            "name": self.name,
            "hardware_type": self.hardware_type_name,
            "protocol": self.protocol_name,
            "profile_id": self.profile_id,
            "settings": settings,
            "status": self.status_name,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "error_message": self.error_message,
            "is_active": self.is_active,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
