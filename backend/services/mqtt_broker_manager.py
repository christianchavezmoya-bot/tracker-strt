"""Runtime control of the embedded MQTT broker (admin toggle)."""
from __future__ import annotations

import logging
import socket
from typing import Optional

import backend.config as cfg
from backend.extensions import db
from backend.models.settings import Setting, SettingScope

logger = logging.getLogger(__name__)

SETTING_KEY = "mqtt_broker_enabled"
_app = None


def configure(app) -> None:
    global _app
    _app = app


def is_broker_enabled(session=None) -> bool:
    sess = session or db.session
    try:
        row = sess.query(Setting).filter_by(key=SETTING_KEY).first()
        if row is not None:
            return bool(row.get_typed_value())
    except Exception:
        pass
    return bool(getattr(cfg, "MQTT_BROKER_ENABLED", False))


def set_broker_enabled(enabled: bool, user_id: int | None = None) -> None:
    row = db.session.query(Setting).filter_by(key=SETTING_KEY).first()
    if not row:
        row = Setting(
            key=SETTING_KEY,
            scope=int(SettingScope.SYSTEM),
            label="Receive data from WiFi nodes",
            description="When ON, this server accepts MQTT tag data on port 1883.",
            value_type="bool",
        )
        db.session.add(row)
    row.set_typed_value(bool(enabled))
    if user_id:
        row.updated_by_id = user_id
    db.session.commit()


def _lan_hint_host() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def wifi_unit_setup_info(request_host: str | None = None) -> dict:
    host = (request_host or _lan_hint_host()).split(":")[0]
    port = int(getattr(cfg, "MQTT_BROKER_PORT", 1883))
    return {
        "title": "WiFi unit settings",
        "broker_host": host,
        "broker_port": port,
        "broker_url": f"mqtt://{host}:{port}",
        "topic": "rssi/data",
        "payload_format": "NodeMAC,TagMAC,RSSI,Battery",
        "example_payload": "00:C0:CA:A1:4B:18,F9:2F:B6:2C:DE:24,-72,98",
        "steps": [
            f"Set MQTT broker address to {host}",
            f"Set port to {port}",
            "Set publish topic to rssi/data",
            "Use CSV payload: NodeMAC,TagMAC,RSSI,Battery",
        ],
        "note": "Use this server address in production — the PC HOLO-MQTT-Broker app is for testing only.",
    }


def start_embedded_broker() -> tuple[bool, str]:
    if not _app:
        return False, "Application not configured"
    from backend.services.mqtt_broker_service import get_mqtt_broker, init_mqtt_broker
    from backend.services.mqtt_tag_ingest import init_mqtt_tag_ingest

    existing = get_mqtt_broker()
    if existing and existing.running:
        return True, f"Broker already running on port {existing.port}"

    ingest = init_mqtt_tag_ingest(app=_app)
    broker = init_mqtt_broker(
        bind=getattr(cfg, "MQTT_BROKER_BIND", "0.0.0.0"),
        port=int(getattr(cfg, "MQTT_BROKER_PORT", 1883)),
        allow_anonymous=getattr(cfg, "MQTT_BROKER_ALLOW_ANONYMOUS", True),
        on_message=ingest.handle_message,
    )
    ok, msg = broker.start()
    if ok:
        logger.info("MQTT broker started via admin control: %s", msg)
    else:
        logger.warning("MQTT broker start failed: %s", msg)
    return ok, msg


def stop_embedded_broker() -> None:
    from backend.services.mqtt_broker_service import get_mqtt_broker

    broker = get_mqtt_broker()
    if broker:
        broker.stop()
        logger.info("MQTT broker stopped via admin control")


def apply_broker_enabled(enabled: bool) -> dict:
    if enabled:
        ok, msg = start_embedded_broker()
    else:
        stop_embedded_broker()
        ok, msg = True, "Broker stopped"
    return broker_status_summary(message=msg, start_ok=ok)


def start_if_configured() -> None:
    if is_broker_enabled():
        start_embedded_broker()


def broker_status_summary(message: str | None = None, start_ok: bool | None = None) -> dict:
    from backend.services.mqtt_broker_service import get_mqtt_broker
    from backend.services.mqtt_tag_ingest import get_mqtt_tag_ingest

    enabled = is_broker_enabled()
    broker = get_mqtt_broker()
    ingest = get_mqtt_tag_ingest()
    running = bool(broker and broker.running)
    port = int(getattr(cfg, "MQTT_BROKER_PORT", 1883))
    bind = getattr(cfg, "MQTT_BROKER_BIND", "0.0.0.0")
    host_hint = _lan_hint_host()

    status = "running" if running else ("enabled" if enabled else "disabled")
    if enabled and not running:
        status = "error"

    out = {
        "enabled": enabled,
        "running": running,
        "status": status,
        "bind": bind,
        "port": port,
        "host_hint": host_hint,
        "broker_url": f"mqtt://{host_hint}:{port}",
        "message_count": broker.message_count if broker else 0,
        "last_error": broker.last_error if broker else None,
        "ingest": ingest.diagnostics() if ingest else None,
    }
    if message:
        out["message"] = message
    if start_ok is not None:
        out["start_ok"] = start_ok
    return out
