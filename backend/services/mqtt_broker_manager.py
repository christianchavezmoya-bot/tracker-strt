"""Runtime control of the embedded MQTT broker (admin toggle)."""
from __future__ import annotations

import logging
import re
import socket
import subprocess
from typing import Optional

import backend.config as cfg
from backend.extensions import db
from backend.models.settings import Setting, SettingScope

logger = logging.getLogger(__name__)

SETTING_KEY = "mqtt_broker_enabled"
ADVERTISED_HOST_KEY = "mqtt_broker_advertised_host"
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


def set_broker_advertised_host(host: str | None, user_id: int | None = None) -> None:
    value = (host or "").strip()
    row = db.session.query(Setting).filter_by(key=ADVERTISED_HOST_KEY).first()
    if not row:
        row = Setting(
            key=ADVERTISED_HOST_KEY,
            scope=int(SettingScope.SYSTEM),
            label="MQTT broker advertised host",
            description="Local LAN IP shown to WiFi nodes for MQTT connection.",
            value_type="string",
        )
        db.session.add(row)
    row.set_typed_value(value)
    if user_id:
        row.updated_by_id = user_id
    db.session.commit()


def get_broker_advertised_host(session=None) -> str:
    sess = session or db.session
    try:
        row = sess.query(Setting).filter_by(key=ADVERTISED_HOST_KEY).first()
        if row is not None:
            value = (row.get_typed_value() or "").strip()
            if value:
                return value
    except Exception:
        pass
    return _lan_hint_host()


def _lan_hint_host() -> str:
    for candidate in _candidate_hosts():
        if candidate.get("recommended"):
            return candidate["ip"]
    for candidate in _candidate_hosts():
        if candidate.get("ip") not in ("127.0.0.1", "0.0.0.0"):
            return candidate["ip"]
    return "127.0.0.1"


def _candidate_hosts() -> list[dict]:
    hosts = _windows_interface_hosts()
    if not hosts:
        hosts = _generic_interface_hosts()
    seen = set()
    out = []
    for item in hosts:
        ip = (item.get("ip") or "").strip()
        if not ip or ip.startswith("127.") or ip in seen:
            continue
        seen.add(ip)
        out.append(item)
    if not out:
        out.append({"label": "Localhost", "ip": "127.0.0.1", "recommended": True})
    return out


def _windows_interface_hosts() -> list[dict]:
    try:
        output = subprocess.check_output(["ipconfig"], text=True, encoding="utf-8", errors="ignore")
    except Exception:
        return []

    results = []
    current = None
    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if not raw_line.startswith(" "):
            current = line.rstrip(":")
            continue
        if "IPv4 Address" not in line and "IPv4-adress" not in line:
            continue
        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
        if not match:
            continue
        ip = match.group(1)
        label = current or ip
        lname = label.lower()
        results.append({
            "label": label,
            "ip": ip,
            "recommended": "ethernet" in lname or "eth" in lname,
        })
    return results


def _generic_interface_hosts() -> list[dict]:
    results = []
    try:
        hostname = socket.gethostname()
        ips = socket.gethostbyname_ex(hostname)[2]
    except Exception:
        ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips = [s.getsockname()[0], *ips]
        s.close()
    except Exception:
        pass
    seen = set()
    for ip in ips:
        if not ip or ip in seen:
            continue
        seen.add(ip)
        results.append({"label": ip, "ip": ip, "recommended": len(results) == 0})
    return results


def wifi_unit_setup_info(request_host: str | None = None) -> dict:
    from backend.services.time_sync_status import time_sync_status_summary

    host = get_broker_advertised_host()
    port = int(getattr(cfg, "MQTT_BROKER_PORT", 1883))
    time_cfg = time_sync_status_summary()
    node_timezone = time_cfg.get("node_timezone", "UTC")
    node_ntp_server = time_cfg.get("node_ntp_server", host)
    node_ntp_mode = time_cfg.get("node_ntp_mode", "lan_server")
    return {
        "title": "WiFi unit settings",
        "broker_host": host,
        "broker_port": port,
        "broker_url": f"mqtt://{host}:{port}",
        "available_hosts": _candidate_hosts(),
        "selected_host": host,
        "topic": "rssi/data",
        "topic_note": "Your units may use a different topic (e.g. strata/v1/bluetooth/...). Check Diagnostics -> Incoming traffic.",
        "payload_format": "NodeMAC,TagMAC,RSSI,Battery (or vendor JSON/array - see Incoming traffic)",
        "example_payload": "00:C0:CA:A1:4B:18,F9:2F:B6:2C:DE:24,-72,98",
        "example_strata_payload": "[1,1750690877,30,273983315172900,1,828033288983,-95]",
        "example_strata_topic": "strata/v1/bluetooth/1/273983315172900",
        "node_timezone": node_timezone,
        "node_ntp_server": node_ntp_server,
        "node_ntp_mode": node_ntp_mode,
        "steps": [
            f"Set MQTT broker address to {host}",
            f"Set port to {port}",
            f"Set node timezone to {node_timezone}",
            f"Set node NTP server to {node_ntp_server}",
            "Point units at this server - topic may vary by firmware",
            "Open Anchors -> Diagnostics -> Incoming traffic to verify raw messages",
        ],
        "note": (
            "Configure broker IP/port plus timezone and NTP on each WiFi unit. "
            "RTLS event timing uses server receive time as truth; node time is kept for diagnostics and drift checks."
        ),
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


def _check_port_listening(host: str, port: int, timeout: float = 1.0) -> bool:
    import socket

    connect_host = host
    if connect_host in ("0.0.0.0", "", "*"):
        connect_host = "127.0.0.1"
    try:
        with socket.create_connection((connect_host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def broker_status_summary(message: str | None = None, start_ok: bool | None = None) -> dict:
    from backend.services.mqtt_broker_service import get_mqtt_broker
    from backend.services.mqtt_tag_ingest import get_mqtt_tag_ingest

    enabled = is_broker_enabled()
    broker = get_mqtt_broker()
    ingest = get_mqtt_tag_ingest()
    running = bool(broker and broker.running)
    port = int(getattr(cfg, "MQTT_BROKER_PORT", 1883))
    bind = getattr(cfg, "MQTT_BROKER_BIND", "0.0.0.0")
    host_hint = get_broker_advertised_host()
    available_hosts = _candidate_hosts()

    status = "running" if running else ("enabled" if enabled else "disabled")
    if enabled and not running:
        status = "error"

    port_reachable = _check_port_listening(host_hint, port) if enabled else False

    out = {
        "enabled": enabled,
        "running": running,
        "status": status,
        "bind": bind,
        "port": port,
        "host_hint": host_hint,
        "broker_url": f"mqtt://{host_hint}:{port}",
        "available_hosts": available_hosts,
        "selected_host": host_hint,
        "port_reachable": port_reachable,
        "message_count": broker.message_count if broker else 0,
        "last_error": broker.last_error if broker else None,
        "ingest": ingest.diagnostics() if ingest else None,
    }
    if message:
        out["message"] = message
    if start_ok is not None:
        out["start_ok"] = start_ok
    return out
