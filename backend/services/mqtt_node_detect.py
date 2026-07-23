"""Detect WiFi nodes from raw MQTT topic/payload before tag parsing."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
import re
from typing import Optional

from backend.extensions import db
from backend.models.tracker import NodeStatus, WifiNode
from backend.services.anchor_sync import ensure_node_pair, touch_node_heartbeat
from backend.services.node_utils import get_node_metadata
from backend.services.time_sync_status import CLOCK_SKEW_WARN_KEY, _setting_value

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


def _extract_node_reported_at(payload: str) -> str | None:
    body = (payload or '').strip()
    if not body:
        return None
    if body.startswith('['):
        try:
            data = json.loads(body)
            if isinstance(data, list) and len(data) >= 2:
                return _epochish_to_iso(data[1])
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    if body.startswith('{'):
        try:
            data = json.loads(body)
            if isinstance(data, dict):
                return (
                    _epochish_to_iso(data.get('timestamp'))
                    or _epochish_to_iso(data.get('ts'))
                    or _epochish_to_iso(data.get('time'))
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    return None


def _extract_clock_skew_seconds(payload: str, *, received_at: datetime | None = None) -> float | None:
    node_iso = _extract_node_reported_at(payload)
    if not node_iso:
        return None
    try:
        node_dt = datetime.fromisoformat(node_iso.replace('Z', '+00:00'))
        if node_dt.tzinfo is None:
            node_dt = node_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    now = received_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return round((now - node_dt).total_seconds(), 3)


def _epochish_to_iso(value) -> str | None:
    if value in (None, ''):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num > 10_000_000_000:
        num = num / 1000.0
    try:
        return datetime.fromtimestamp(num, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def register_node_from_mqtt(
    node_key: str,
    hints: dict | None = None,
    *,
    client_id: str | None = None,
    payload: str | None = None,
    client_ip: str | None = None,
) -> WifiNode:
    """Create or update WifiNode from detected MQTT traffic; sync anchor row."""
    hints = hints or {}
    original_key = node_key.upper()
    key = original_key
    sess = db.session

    resolved_ip = client_ip
    if client_id:
        from backend.services.mqtt_client_registry import link_node_key, get_ip_for_client
        link_node_key(original_key, client_id, client_ip=client_ip)
        if not resolved_ip:
            resolved_ip = get_ip_for_client(client_id)

    from backend.services.node_anchor_merge import (
        record_strata_alias,
        resolve_canonical_node_key,
    )

    key, canonical = resolve_canonical_node_key(
        key, client_ip=resolved_ip, session=sess,
    )
    if canonical and key != original_key:
        record_strata_alias(canonical, original_key, hints.get("strata_node_id"))
        link_node_key(original_key, client_id or "", client_ip=resolved_ip)

    node = sess.query(WifiNode).filter_by(mac_address=key).first()
    meta = get_node_metadata(node) if node else {}

    if client_id:
        from backend.services.mqtt_client_registry import link_node_key, get_ip_for_client
        link_node_key(key, client_id, client_ip=resolved_ip or client_ip)
        meta["last_client_id"] = client_id
        ip = resolved_ip or get_ip_for_client(client_id)
        if ip:
            meta["node_ip"] = ip
            meta["physical_unit_ip"] = ip

    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    meta.setdefault("first_discovered_at", now_iso)
    meta["last_seen_at"] = now_iso
    meta["messages_total"] = int(meta.get("messages_total") or 0) + 1
    if payload:
        meta["last_payload"] = (payload or "")[:500]
        meta["last_payload_at"] = now_iso
        node_reported_at = _extract_node_reported_at(payload)
        if node_reported_at:
            meta["last_node_reported_at"] = node_reported_at
        skew = _extract_clock_skew_seconds(payload, received_at=now_utc)
        if skew is not None:
            meta["last_clock_skew_seconds"] = skew
            warn_threshold = float(meta.get("clock_skew_warn_seconds") or _setting_value(CLOCK_SKEW_WARN_KEY, 10) or 10)
            meta["clock_skew_warn_seconds"] = warn_threshold
            meta["clock_skew_warning"] = abs(skew) >= warn_threshold

    strata_id = hints.get("strata_node_id")
    default_name = f"STRATA-{strata_id[-6:]}" if strata_id else f"Node-{key[-8:]}"

    if not node:
        meta.update({
            "placed_on_map": False,
            "source": "mqtt_traffic",
            "mqtt_auto_detected": True,
            "mqtt_acknowledged": False,
            "payload_format": hints.get("payload_format", "unknown"),
            "last_mqtt_topic": hints.get("topic"),
            "first_discovered_at": meta.get("first_discovered_at") or now_iso,
            "last_seen_at": now_iso,
            "messages_total": int(meta.get("messages_total") or 0),
        })
        if strata_id:
            meta.setdefault("canonical_strata_id", meta.get("canonical_strata_id") or strata_id)
            if original_key == key:
                meta["strata_node_id"] = meta.get("canonical_strata_id")
        if resolved_ip:
            meta["physical_unit_ip"] = resolved_ip
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
            meta.setdefault("canonical_strata_id", meta.get("canonical_strata_id") or strata_id)
            if original_key == key:
                meta["strata_node_id"] = meta.get("canonical_strata_id")
        if resolved_ip:
            meta["physical_unit_ip"] = resolved_ip
        meta.setdefault("mqtt_auto_detected", True)
        node.metadata_json = json.dumps(meta)

    if original_key != key:
        record_strata_alias(node, original_key, hints.get("strata_node_id"))

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
