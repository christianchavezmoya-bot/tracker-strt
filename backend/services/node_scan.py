"""Anchor scan — refresh node list from MQTT traffic + DB."""
from __future__ import annotations

from datetime import datetime

from backend.extensions import db
from backend.models.tracker import WifiNode
from backend.services.mqtt_client_registry import get_ip_for_node, get_iface_for_node
from backend.services.mqtt_traffic_log import get_mqtt_traffic_log
from backend.services.net_interface_resolve import interface_label
from backend.services.node_ip_diagnostics import build_ip_conflict_map, enrich_scan_item
from backend.services.node_utils import get_node_metadata, is_node_placed, is_node_offline


def _node_ip(node: WifiNode) -> str | None:
    meta = get_node_metadata(node)
    return meta.get("node_ip") or get_ip_for_node(node.mac_address)


def _commission_state(node: WifiNode) -> str:
    meta = get_node_metadata(node)
    if meta.get("decommissioned"):
        return "decommissioned"
    if meta.get("operational_state") == "inactive":
        return "inactive"
    if is_node_placed(node) and node.status == 1:
        return "active"
    if meta.get("mqtt_acknowledged"):
        return "awaiting_placement"
    if meta.get("mqtt_auto_detected"):
        return "detected"
    return "manual"


def _server_interface(node: WifiNode) -> str | None:
    meta = get_node_metadata(node)
    return meta.get("server_interface") or get_iface_for_node(node.mac_address)


def scan_nodes(session=None) -> dict:
    """Build scan snapshot for commission table (name + IP required columns)."""
    sess = session or db.session
    nodes = sess.query(WifiNode).order_by(WifiNode.last_heartbeat.desc().nullslast(), WifiNode.id.desc()).all()
    traffic = get_mqtt_traffic_log().summary()
    items = []
    for n in nodes:
        meta = get_node_metadata(n)
        ip = _node_ip(n)
        iface = _server_interface(n)
        iface_label = meta.get("server_interface_label") or (interface_label(ip, iface) if iface else None)
        items.append({
            "node_id": n.id,
            "name": n.assigned_name or f"STRATA-{str(meta.get('strata_node_id', ''))[-6:]}" or n.mac_address,
            "node_ip": ip or "—",
            "client_ip": ip or "—",
            "server_interface": iface or "—",
            "server_interface_label": iface_label or "—",
            "mac_address": n.mac_address,
            "strata_node_id": meta.get("strata_node_id"),
            "last_heard_at": n.last_heartbeat.isoformat() if n.last_heartbeat else None,
            "last_timestamp": n.last_heartbeat.isoformat() if n.last_heartbeat else None,
            "messages_total": meta.get("messages_total"),
            "payload_format": meta.get("payload_format", "unknown"),
            "commission_state": _commission_state(n),
            "mqtt_acknowledged": bool(meta.get("mqtt_acknowledged")),
            "placed_on_map": is_node_placed(n),
            "online": not is_node_offline(n),
            "status": n.status,
            "pos_x": n.pos_x,
            "pos_y": n.pos_y,
            "pos_z": n.pos_z,
            "last_topic": meta.get("last_mqtt_topic"),
            "last_payload": meta.get("last_payload"),
            "last_client_id": meta.get("last_client_id"),
        })
    conflicts = build_ip_conflict_map(items)
    items = [enrich_scan_item(item, conflicts) for item in items]
    return {
        "scanned_at": datetime.utcnow().isoformat(),
        "total": len(items),
        "traffic": traffic,
        "ip_conflicts": conflicts,
        "items": items,
    }


def commission_queue(session=None) -> dict:
    sess = session or db.session
    scan = scan_nodes(sess)
    buckets = {
        "detected": [],
        "awaiting_placement": [],
        "active": [],
        "inactive": [],
        "decommissioned": [],
    }
    for item in scan["items"]:
        state = item["commission_state"]
        if state in buckets:
            buckets[state].append(item)
        else:
            buckets["detected"].append(item)
    return {"scanned_at": scan["scanned_at"], "traffic": scan["traffic"], **buckets}
