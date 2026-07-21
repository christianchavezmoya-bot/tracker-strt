"""Persist Node Reader settings, BlueApro node profiles, and tag profiles."""
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
    # BlueApro / WiFi 6/6E node (vendor firmware)
    node_host: str = "192.168.4.1"
    node_port: int = 80
    node_use_https: bool = False
    node_username: str = "admin"
    node_password: str = ""
    node_serial: str = ""
    node_model: str = "BlueApro 6/6E"

    # PC network interface for scan + HTTP bind + push URI
    network_interface_key: str = ""   # e.g. "Wi-Fi|10.7.15.76"
    network_bind_ip: str = ""         # cached IP for selected interface

    # HTTP mode: pull = PC GETs node API; push = node POSTs to PC listener
    http_mode: str = "pull"  # pull | push
    devices_path: str = "/api/ble/devices"
    health_path: str = "/api/system"
    scan_start_path: str = "/api/ble/scanner/start"
    scan_stop_path: str = "/api/ble/scanner/stop"

    # Local ingest server (push mode + optional dashboard)
    listen_host: str = "0.0.0.0"
    listen_port: int = 8765
    listen_path: str = "/ingest/blueapro"

    poll_interval_sec: float = 2.0
    discovery_ports: list = field(default_factory=lambda: [80, 8080, 8765, 5000])

    # Optional uplink to central HOLO-RTLS
    uplink_enabled: bool = False
    uplink_host: str = "127.0.0.1"
    uplink_port: int = 5000
    uplink_transport: str = "http"
    uplink_mqtt_port: int = 1883
    uplink_api_key: str = "scanner-dev-key"
    uplink_anchor_mac: str = ""

    saved_nodes: list = field(default_factory=list)
    admin_email: str = ""
    admin_password: str = ""


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
