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
