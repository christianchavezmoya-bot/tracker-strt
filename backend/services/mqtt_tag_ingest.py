"""MQTT tag ingest — parse WiFi node publishes and feed positioning pipeline."""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
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

    def handle_message(
        self, client_id: str, topic: str, payload: str, client_ip: str | None = None,
    ) -> None:
        from backend.services.mqtt_node_detect import (
            detect_node_from_mqtt,
            register_node_from_mqtt,
            _extract_clock_skew_seconds,
            _extract_node_reported_at,
        )
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
        received_at = datetime.now(timezone.utc)
        node_reported_at = _extract_node_reported_at(payload)
        clock_skew_seconds = _extract_clock_skew_seconds(payload, received_at=received_at)
        clock_skew_warning = abs(clock_skew_seconds) >= 10 if clock_skew_seconds is not None else False

        if node_key and self.app:
            with self.app.app_context():
                try:
                    from backend.services.mqtt_client_registry import (
                        get_ip_for_node, link_node_key, note_node_ip, register_client,
                    )
                    from backend.services.net_interface_resolve import interface_label, resolve_server_interface
                    from backend.services.node_presence import log_node_presence, update_node_connection_metadata
                    from backend.services.node_utils import get_node_metadata, is_node_active_for_mqtt
                    from backend.services.mqtt_node_detect import _extract_strata_rssi

                    if client_ip:
                        register_client(client_id or "", client_ip)
                    server_iface = resolve_server_interface(client_ip) if client_ip else None
                    iface_label = interface_label(client_ip, server_iface) if client_ip else None
                    link_node_key(
                        node_key, client_id or "",
                        client_ip=client_ip, server_interface=server_iface,
                    )
                    node = register_node_from_mqtt(
                        node_key, detect_hints, client_id=client_id, payload=payload,
                    )
                    node_id = node.id
                    try:
                        from backend.services.time_sync_status import CLOCK_SKEW_WARN_KEY, _setting_value
                        warn_threshold = float(_setting_value(CLOCK_SKEW_WARN_KEY, 10) or 10)
                    except Exception:
                        warn_threshold = 10.0
                    if clock_skew_seconds is not None:
                        clock_skew_warning = abs(clock_skew_seconds) >= warn_threshold
                        meta = get_node_metadata(node)
                        meta['last_clock_skew_seconds'] = clock_skew_seconds
                        meta['clock_skew_warning'] = clock_skew_warning
                        meta['clock_skew_warn_seconds'] = warn_threshold
                        if node_reported_at:
                            meta['last_node_reported_at'] = node_reported_at
                        node.metadata_json = __import__('json').dumps(meta)
                    rssi = _extract_strata_rssi(payload or "")
                    ip = client_ip or get_ip_for_node(node_key)
                    if ip or server_iface:
                        note_node_ip(node_key, ip, server_interface=server_iface)
                        update_node_connection_metadata(
                            node, ip=ip, server_interface=server_iface,
                            server_interface_label=iface_label,
                        )
                    log_node_presence(node, online=True, rssi=rssi, node_ip=ip)
                    db.session.commit()
                    mac = node_key.upper()
                    with self._lock:
                        self.per_node_counts[mac] += 1
                        self.per_node_last_at[mac] = datetime.utcnow()
                except Exception:
                    logger.exception("Failed to register node from MQTT %s", node_key)
                    db.session.rollback()

        from backend.services.mqtt_client_registry import get_ip_for_node, get_iface_for_node
        from backend.services.net_interface_resolve import interface_label, resolve_server_interface

        resolved_iface = None
        if client_ip:
            resolved_iface = resolve_server_interface(client_ip)
        elif node_key:
            resolved_iface = get_iface_for_node(node_key)

        get_mqtt_traffic_log().append(
            client_id=client_id,
            topic=topic or "",
            payload=payload or "",
            node_key=node_key,
            node_id=node_id,
            client_ip=client_ip or (get_ip_for_node(node_key) if node_key else None),
            server_interface=resolved_iface,
            parsed=parsed,
            parse_count=len(readings),
            payload_format=detect_hints.get("payload_format", "unknown"),
            node_reported_at=node_reported_at,
            clock_skew_seconds=clock_skew_seconds,
            clock_skew_warning=clock_skew_warning,
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
        from backend.models.tracker import WifiNode
        from backend.services.node_utils import is_node_active_for_mqtt

        pos_svc = WifiPositioningService(db.session)
        for anchor_mac, batch in grouped.items():
            try:
                node, _anchor = ensure_node_pair(anchor_mac)
                if not is_node_active_for_mqtt(node):
                    logger.debug("Ignoring MQTT detections from non-active node %s", anchor_mac)
                    touch_node_heartbeat(anchor_mac)
                    continue
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
