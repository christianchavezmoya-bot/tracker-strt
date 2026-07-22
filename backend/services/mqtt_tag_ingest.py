"""MQTT tag ingest — parse WiFi node publishes and feed positioning pipeline."""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from datetime import datetime
from typing import Optional

from backend.extensions import db
from backend.services.anchor_sync import ensure_node_pair, touch_node_heartbeat
from backend.services.mqtt_tag_parse import (
    group_by_anchor,
    parse_mqtt_payload,
    readings_to_detections,
)
from backend.services.wifi_positioning import WifiPositioningService

logger = logging.getLogger(__name__)


class MqttTagIngestService:
    """Handle MQTT publishes from WiFi scanner nodes."""

    def __init__(self, app=None):
        self.app = app
        self._lock = threading.Lock()
        self.message_count = 0
        self.last_message_at: Optional[datetime] = None
        self.last_payload: str = ""
        self.last_topic: str = ""
        self.per_node_counts: dict[str, int] = defaultdict(int)
        self.per_node_last_at: dict[str, datetime] = {}
        self.per_node_last_payload: dict[str, str] = {}
        self.per_node_last_topic: dict[str, str] = {}

    def handle_message(self, client_id: str, topic: str, payload: str) -> None:
        from backend.services.mqtt_node_detect import detect_node_from_mqtt, register_node_from_mqtt
        from backend.services.mqtt_traffic_log import get_mqtt_traffic_log

        with self._lock:
            self.message_count += 1
            self.last_message_at = datetime.utcnow()
            self.last_payload = (payload or "")[:500]
            self.last_topic = topic or ""

        node_key, detect_hints = detect_node_from_mqtt(topic, payload)
        node_id = None
        if node_key:
            with self._lock:
                mac = node_key.upper()
                self.per_node_last_payload[mac] = (payload or "")[:500]
                self.per_node_last_topic[mac] = topic or ""

        readings = parse_mqtt_payload(payload, topic)
        parsed = len(readings) > 0

        if node_key and self.app:
            with self.app.app_context():
                try:
                    from backend.services.mqtt_client_registry import get_ip_for_node, link_node_key
                    from backend.services.node_presence import log_node_presence, update_node_ip_metadata
                    from backend.services.mqtt_node_detect import _extract_strata_rssi

                    link_node_key(node_key, client_id or "")
                    node = register_node_from_mqtt(
                        node_key, detect_hints, client_id=client_id, payload=payload,
                    )
                    node_id = node.id
                    rssi = _extract_strata_rssi(payload or "")
                    ip = get_ip_for_node(node_key)
                    if ip:
                        update_node_ip_metadata(node, ip)
                    log_node_presence(node, online=True, rssi=rssi, node_ip=ip)
                    db.session.commit()
                    mac = node_key.upper()
                    with self._lock:
                        self.per_node_counts[mac] += 1
                        self.per_node_last_at[mac] = datetime.utcnow()
                except Exception:
                    logger.exception("Failed to register node from MQTT %s", node_key)
                    db.session.rollback()

        get_mqtt_traffic_log().append(
            client_id=client_id,
            topic=topic or "",
            payload=payload or "",
            node_key=node_key,
            node_id=node_id,
            parsed=parsed,
            parse_count=len(readings),
            payload_format=detect_hints.get("payload_format", "unknown"),
        )

        if not readings:
            logger.debug("MQTT message had no parseable tags (%s)", topic)
            return

        grouped = group_by_anchor(readings)
        if not grouped:
            logger.debug("MQTT readings missing anchor MAC (%s)", topic)
            return

        with self._lock:
            for anchor_mac in grouped:
                mac = anchor_mac.upper()
                self.per_node_last_payload[mac] = (payload or "")[:500]
                self.per_node_last_topic[mac] = topic or "rssi/data"

        if self.app:
            with self.app.app_context():
                self._ingest_grouped(grouped)
        else:
            self._ingest_grouped(grouped)

    def _ingest_grouped(self, grouped: dict[str, list]) -> None:
        pos_svc = WifiPositioningService(db.session)
        for anchor_mac, batch in grouped.items():
            try:
                ensure_node_pair(anchor_mac)
                detections = readings_to_detections(batch)
                pos_svc.process_scan_batch(anchor_mac, detections)
                touch_node_heartbeat(anchor_mac)
                self.per_node_counts[anchor_mac] += 1
                now = datetime.utcnow()
                self.per_node_last_at[anchor_mac] = now
            except Exception:
                logger.exception("Failed to ingest MQTT batch from %s", anchor_mac)
                db.session.rollback()
                continue

        try:
            fixes = pos_svc.compute_all_positions()
            if fixes:
                from backend.api.scanner import _sync_scanner_fixes_to_core
                _sync_scanner_fixes_to_core(fixes)
            else:
                db.session.commit()
        except Exception:
            logger.exception("Failed to compute positions after MQTT ingest")
            db.session.rollback()

    def diagnostics(self) -> dict:
        return {
            "message_count": self.message_count,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "last_topic": self.last_topic,
            "last_payload": self.last_payload,
            "per_node_counts": dict(self.per_node_counts),
            "per_node_last_at": {
                mac: ts.isoformat() for mac, ts in self.per_node_last_at.items()
            },
            "per_node_last_payload": dict(self.per_node_last_payload),
            "per_node_last_topic": dict(self.per_node_last_topic),
        }


_ingest: Optional[MqttTagIngestService] = None


def get_mqtt_tag_ingest() -> Optional[MqttTagIngestService]:
    return _ingest


def init_mqtt_tag_ingest(app=None) -> MqttTagIngestService:
    global _ingest
    if _ingest is None:
        _ingest = MqttTagIngestService(app=app)
    elif app is not None:
        _ingest.app = app
    return _ingest


def reset_mqtt_tag_ingest() -> None:
    """Clear singleton (test isolation)."""
    global _ingest
    _ingest = None
