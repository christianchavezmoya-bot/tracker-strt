"""Persist node reader settings and per-tag profiles."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".config"
    d = base / "HOLO-RTLS" / "NodeReader"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_FILE = _config_dir() / "settings.json"
TAGS_FILE = _config_dir() / "tags.json"


@dataclass
class AppConfig:
    server_host: str = "127.0.0.1"
    server_port: int = 5000
    transport: str = "http"  # http | mqtt
    mqtt_port: int = 1883
    mqtt_use_tls: bool = False
    mqtt_topic: str = "rssi/data"
    scanner_api_key: str = "scanner-dev-key"
    anchor_mac: str = ""
    anchor_name: str = "PC-Reader"
    rssi_min: int = -90
    scan_interval_sec: float = 1.5
    tags_only: bool = False
    forward_to_server: bool = True
    admin_email: str = ""
    admin_password: str = ""  # stored locally for convenience; optional
    saved_nodes: list = field(default_factory=list)


@dataclass
class TagProfile:
    mac: str
    display_name: str = ""
    scan_type: str = "UNKNOWN_BLE"
    moko_password: str = ""
    notes: str = ""
    enabled: bool = True


def load_config() -> AppConfig:
    if not CONFIG_FILE.exists():
        return AppConfig()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return AppConfig(**{k: v for k, v in data.items() if k in AppConfig.__dataclass_fields__})
    except Exception:
        return AppConfig()


def save_config(cfg: AppConfig) -> None:
    CONFIG_FILE.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")


def load_tag_profiles() -> dict[str, TagProfile]:
    if not TAGS_FILE.exists():
        return {}
    try:
        raw = json.loads(TAGS_FILE.read_text(encoding="utf-8"))
        return {mac: TagProfile(**v) for mac, v in raw.items()}
    except Exception:
        return {}


def save_tag_profiles(profiles: dict[str, TagProfile]) -> None:
    TAGS_FILE.write_text(
        json.dumps({mac: asdict(p) for mac, p in profiles.items()}, indent=2),
        encoding="utf-8",
    )
