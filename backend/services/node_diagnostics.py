"""Per-node network diagnostics — MQTT presence, RSSI stats, message rates."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func

from backend.extensions import db
from backend.models.detection import DetectionEvent, WifiAnchor
from backend.models.tracker import WifiNode
from backend.services.mqtt_broker_manager import broker_status_summary
from backend.services.mqtt_tag_ingest import get_mqtt_tag_ingest
from backend.services.node_utils import is_node_placed, is_node_offline

ONLINE_THRESHOLD_SEC = 60.0
WEAK_THRESHOLD_SEC = 120.0


def _parse_since(since: str) -> timedelta:
    since = (since or "24h").strip().lower()
    if since.endswith("h"):
        return timedelta(hours=max(float(since[:-1] or 24), 0.1))
    if since.endswith("m"):
        return timedelta(minutes=max(float(since[:-1] or 60), 1))
    if since.endswith("d"):
        return timedelta(days=max(float(since[:-1] or 1), 0.01))
    return timedelta(hours=24)


def _heartbeat_age_seconds(node: WifiNode) -> float | None:
    if not node.last_heartbeat:
        return None
    hb = node.last_heartbeat
    if hb.tzinfo is not None:
        hb = hb.replace(tzinfo=None)
    return max(0.0, (datetime.utcnow() - hb).total_seconds())


def _connectivity_label(age_sec: float | None, offline_flag: bool) -> tuple[str, bool]:
    if offline_flag:
        return "offline", False
    if age_sec is None:
        return "unknown", False
    if age_sec <= ONLINE_THRESHOLD_SEC:
        return "online", True
    if age_sec <= WEAK_THRESHOLD_SEC:
        return "weak", False
    return "offline", False


def _anchor_for_node(session, mac: str) -> WifiAnchor | None:
    return session.query(WifiAnchor).filter_by(mac_address=mac.upper()).first()


def _ingest_hints(mac: str) -> dict:
    ingest = get_mqtt_tag_ingest()
    if not ingest:
        return {}
    mac = mac.upper()
    with ingest._lock:
        return {
            "messages_total": int(ingest.per_node_counts.get(mac, 0)),
            "last_payload": (ingest.per_node_last_payload or {}).get(mac),
            "last_topic": (ingest.per_node_last_topic or {}).get(mac),
            "ingest_last_at": (
                ingest.per_node_last_at[mac].isoformat()
                if mac in ingest.per_node_last_at
                else None
            ),
        }


def compute_node_diagnostics(node: WifiNode, session=None) -> dict:
    session = session or db.session
    mac = node.mac_address.upper()
    age = _heartbeat_age_seconds(node)
    offline_flag = is_node_offline(node)
    status_label, online = _connectivity_label(age, offline_flag)
    hints = _ingest_hints(mac)
    anchor = _anchor_for_node(session, mac)

    since = datetime.utcnow() - timedelta(hours=1)
    messages_last_hour = 0
    avg_rssi = None
    tags_recent = 0
    if anchor:
        messages_last_hour = (
            session.query(DetectionEvent)
            .filter(DetectionEvent.anchor_id == anchor.id, DetectionEvent.timestamp >= since)
            .count()
        )
        avg_rssi = (
            session.query(func.avg(DetectionEvent.rssi))
            .filter(DetectionEvent.anchor_id == anchor.id, DetectionEvent.timestamp >= since)
            .scalar()
        )
        tags_recent = (
            session.query(func.count(func.distinct(DetectionEvent.mac_address)))
            .filter(DetectionEvent.anchor_id == anchor.id, DetectionEvent.timestamp >= since)
            .scalar()
            or 0
        )

    return {
        "node_id": node.id,
        "mac_address": mac,
        "name": node.assigned_name,
        "placed_on_map": is_node_placed(node),
        "online": online,
        "connectivity": status_label,
        "last_heard_at": node.last_heartbeat.isoformat() if node.last_heartbeat else hints.get("ingest_last_at"),
        "seconds_since_last": round(age, 1) if age is not None else None,
        "messages_total": hints.get("messages_total", 0),
        "messages_last_hour": messages_last_hour,
        "msg_rate_per_hour": float(messages_last_hour),
        "avg_rssi": round(float(avg_rssi), 1) if avg_rssi is not None else None,
        "tags_seen_last_hour": int(tags_recent),
        "last_payload": hints.get("last_payload"),
        "last_topic": hints.get("last_topic") or "rssi/data",
        "broker": broker_status_summary(),
    }


def compute_all_diagnostics(session=None) -> dict:
    session = session or db.session
    nodes = session.query(WifiNode).order_by(WifiNode.id.desc()).all()
    items = [compute_node_diagnostics(n, session) for n in nodes]
    online = sum(1 for i in items if i["connectivity"] == "online")
    weak = sum(1 for i in items if i["connectivity"] == "weak")
    offline = sum(1 for i in items if i["connectivity"] in ("offline", "unknown"))
    broker = broker_status_summary()
    ingest = get_mqtt_tag_ingest()
    return {
        "broker": broker,
        "summary": {
            "total": len(items),
            "online": online,
            "weak": weak,
            "offline": offline,
            "broker_running": broker.get("running"),
        },
        "ingest": ingest.diagnostics() if ingest else None,
        "nodes": items,
        "timestamp": datetime.utcnow().isoformat(),
    }


def compute_node_stats(node: WifiNode, since: str = "24h", session=None) -> dict:
    session = session or db.session
    window = _parse_since(since)
    cutoff = datetime.utcnow() - window
    anchor = _anchor_for_node(session, node.mac_address)

    if not anchor:
        return {
            "node_id": node.id,
            "mac_address": node.mac_address,
            "since": since,
            "detection_count": 0,
            "unique_tags": 0,
            "avg_rssi": None,
            "min_rssi": None,
            "max_rssi": None,
        }

    base = session.query(DetectionEvent).filter(
        DetectionEvent.anchor_id == anchor.id,
        DetectionEvent.timestamp >= cutoff,
    )
    detection_count = base.count()
    unique_tags = (
        session.query(func.count(func.distinct(DetectionEvent.mac_address)))
        .filter(DetectionEvent.anchor_id == anchor.id, DetectionEvent.timestamp >= cutoff)
        .scalar()
        or 0
    )
    agg = session.query(
        func.avg(DetectionEvent.rssi),
        func.min(DetectionEvent.rssi),
        func.max(DetectionEvent.rssi),
    ).filter(
        DetectionEvent.anchor_id == anchor.id,
        DetectionEvent.timestamp >= cutoff,
    ).one()

    return {
        "node_id": node.id,
        "mac_address": node.mac_address,
        "since": since,
        "detection_count": detection_count,
        "unique_tags": int(unique_tags),
        "avg_rssi": round(float(agg[0]), 1) if agg[0] is not None else None,
        "min_rssi": round(float(agg[1]), 1) if agg[1] is not None else None,
        "max_rssi": round(float(agg[2]), 1) if agg[2] is not None else None,
    }
