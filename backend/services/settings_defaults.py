"""Default setting keys and values for fresh installs and GET fallbacks."""
from backend.models.settings import SettingScope

# Keys used by alert engine, dashboard, and settings UI (subset of settings.html DEFAULT_SETTINGS)
SETTING_DEFAULTS: dict[str, dict] = {
    "proximity_meters": {
        "value": "2.0",
        "value_type": "float",
        "scope": SettingScope.ALERT,
        "label": "Proximity Alert (m)",
    },
    "no_signal_timeout": {
        "value": "120",
        "value_type": "int",
        "scope": SettingScope.ALERT,
        "label": "No Signal Timeout (s)",
    },
    "low_battery_threshold": {
        "value": "20",
        "value_type": "int",
        "scope": SettingScope.ALERT,
        "label": "Low Battery (%)",
    },
    "no_movement_timeout": {
        "value": "30",
        "value_type": "int",
        "scope": SettingScope.ALERT,
        "label": "No Movement Timeout (min)",
    },
    "site_lat": {
        "value": "-25.2744",
        "value_type": "float",
        "scope": SettingScope.BUSINESS,
        "label": "Site latitude (regional map)",
    },
    "site_lng": {
        "value": "133.7751",
        "value_type": "float",
        "scope": SettingScope.BUSINESS,
        "label": "Site longitude (regional map)",
    },
    "site_zoom": {
        "value": "5",
        "value_type": "int",
        "scope": SettingScope.BUSINESS,
        "label": "Regional map zoom",
    },
    "display_timezone": {
        "value": "UTC",
        "value_type": "string",
        "scope": SettingScope.SYSTEM,
        "label": "Display timezone",
    },
    "node_timezone": {
        "value": "UTC",
        "value_type": "string",
        "scope": SettingScope.SYSTEM,
        "label": "Default node timezone",
    },
    "node_ntp_mode": {
        "value": "lan_server",
        "value_type": "string",
        "scope": SettingScope.SYSTEM,
        "label": "Node NTP mode",
    },
    "node_ntp_server": {
        "value": "",
        "value_type": "string",
        "scope": SettingScope.SYSTEM,
        "label": "Node NTP server",
    },
    "node_clock_skew_warn_seconds": {
        "value": "10",
        "value_type": "int",
        "scope": SettingScope.SYSTEM,
        "label": "Node clock skew warning threshold (s)",
    },
}


def default_setting_dict(key: str) -> dict | None:
    """Synthetic setting payload when row is missing but key is known."""
    meta = SETTING_DEFAULTS.get(key)
    if not meta:
        return None
    return {
        "key": key,
        "value": meta["value"],
        "value_type": meta["value_type"],
        "scope": int(meta["scope"]),
        "label": meta.get("label"),
        "is_default": True,
    }
