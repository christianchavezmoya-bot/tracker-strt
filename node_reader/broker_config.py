"""Persist MQTT broker app settings."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def _config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".config"
    d = base / "HOLO-RTLS" / "MqttBroker"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_FILE = _config_dir() / "settings.json"


@dataclass
class BrokerConfig:
    network_interface_key: str = ""
    network_bind_ip: str = "10.60.1.5"
    broker_bind: str = "0.0.0.0"
    broker_port: int = 1883
    auto_start: bool = False


def load_config() -> BrokerConfig:
    if not CONFIG_FILE.exists():
        return BrokerConfig()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return BrokerConfig(**{k: v for k, v in data.items() if k in BrokerConfig.__dataclass_fields__})
    except Exception:
        return BrokerConfig()


def save_config(cfg: BrokerConfig) -> None:
    CONFIG_FILE.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
