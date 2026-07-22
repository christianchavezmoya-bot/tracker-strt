"""Detect WiFi nodes from raw MQTT topic/payload before tag parsing."""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from backend.extensions import db
from backend.models.tracker import NodeStatus, WifiNode
from backend.services.anchor_sync import ensure_node_pair, touch_node_heartbeat
from backend.services.node_utils import get_node_metadata

logger = logging.getLogger(__name__)

_STRATA_TOPIC_RE = re.compile(
    r"^strata/v\d+/bluetooth(?:/[^/]+)*?/(?P<node_id>\d+)\s*$",
    re.I,
)


def detect_node_from_mqtt(topic: str, payload: str) -> tuple[Optional[str], dict]:
    """
    Return (node_key, hints) for auto-registration.
    node_key is stored in WifiNode.mac_address (may be STRATA:id or real MAC).
    """
    topic = (topic or "").strip()
    body = (payload or "").strip()
    hints: dict = {"topic": topic, "payload_format": "unknown"}

    m = _STRATA_TOPIC_RE.match(topic)
    if m:
        node_id = m.group("node_id")
        hints["payload_format"] = "strata_v1_array"
        hints["strata_node_id"] = node_id
        return f"STRATA:{node_id}", hints

    if body.startswith("["):
        try:
            data = json.loads(body)
            if isinstance(data, list) and len(data) >= 4:
                node_id = str(int(data[3]))
                hints["payload_format"] = "strata_v1_array"
                hints["strata_node_id"] = node_id
                return f"STRATA:{node_id}", hints
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    if "," in body and not body.startswith(("{", "[")):
        parts = [p.strip() for p in body.split(",")]
        if len(parts) >= 3:
            anchor = _norm_mac(parts[0])
            if anchor:
                hints["payload_format"] = "csv_holo"
                return anchor, hints

    if topic.startswith("strata/"):
        parts = [p for p in topic.split("/") if p]
        if parts:
            node_id = parts[-1]
            if node_id.isdigit():
                hints["payload_format"] = "strata_v1_array"
                hints["strata_node_id"] = node_id
                return f"STRATA:{node_id}", hints

    return None, hints


def register_node_from_mqtt(
    node_key: str,
    hints: dict | None = None,
    *,
    client_id: str | None = None,
    payload: str | None = None,
) -> WifiNode:
    """Create or update WifiNode from detected MQTT traffic; sync anchor row."""
    hints = hints or {}
    key = node_key.upper()
    sess = db.session
    node = sess.query(WifiNode).filter_by(mac_address=key).first()
    meta = get_node_metadata(node) if node else {}

    if client_id:
        from backend.services.mqtt_client_registry import link_node_key, get_ip_for_client
        link_node_key(key, client_id)
        meta["last_client_id"] = client_id
        ip = get_ip_for_client(client_id)
        if ip:
            meta["node_ip"] = ip

    if payload:
        meta["last_payload"] = (payload or "")[:500]

    strata_id = hints.get("strata_node_id")
    default_name = f"STRATA-{strata_id[-6:]}" if strata_id else f"Node-{key[-8:]}"

    if not node:
        meta = {
            "placed_on_map": False,
            "source": "mqtt_traffic",
            "mqtt_auto_detected": True,
            "mqtt_acknowledged": False,
            "payload_format": hints.get("payload_format", "unknown"),
            "last_mqtt_topic": hints.get("topic"),
        }
        if strata_id:
            meta["strata_node_id"] = strata_id
        node = WifiNode(
            mac_address=key,
            assigned_name=default_name,
            status=int(NodeStatus.CALIBRATING),
            metadata_json=json.dumps(meta),
        )
        sess.add(node)
        sess.flush()
        logger.info("Auto-detected WiFi node from MQTT: %s", key)
    else:
        meta["last_mqtt_topic"] = hints.get("topic") or meta.get("last_mqtt_topic")
        fmt = hints.get("payload_format")
        if fmt and fmt != "unknown":
            meta["payload_format"] = fmt
        if strata_id:
            meta["strata_node_id"] = strata_id
        meta.setdefault("mqtt_auto_detected", True)
        node.metadata_json = json.dumps(meta)

    ensure_node_pair(key)
    touch_node_heartbeat(key)
    try:
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    return node


def acknowledge_mqtt_node(node: WifiNode, user_label: str | None = None, node_ip: str | None = None) -> WifiNode:
    """Operator confirms a detected node is a real anchor."""
    meta = get_node_metadata(node)
    meta["mqtt_acknowledged"] = True
    if node_ip:
        meta["node_ip"] = node_ip.strip()
    if user_label:
        node.assigned_name = user_label.strip()
    node.metadata_json = json.dumps(meta)
    if node.status == int(NodeStatus.CALIBRATING):
        node.status = int(NodeStatus.ACTIVE)
    db.session.commit()
    return node


def _extract_strata_rssi(payload: str) -> float | None:
    if not payload or not payload.strip().startswith("["):
        return None
    try:
        data = json.loads(payload)
        if isinstance(data, list) and len(data) >= 7:
            return float(data[6])
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _norm_mac(mac: str) -> str:
    mac = (mac or "").strip().upper()
    if not mac:
        return ""
    if ":" in mac or "-" in mac:
        return mac.replace("-", ":")
    if len(mac) == 12 and re.fullmatch(r"[0-9A-F]{12}", mac):
        return ":".join(mac[i : i + 2] for i in range(0, 12, 2))
    return mac
