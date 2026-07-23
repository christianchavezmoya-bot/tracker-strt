from __future__ import annotations

from datetime import datetime

from backend.extensions import db
from backend.models.tracker import WifiNode
from backend.services.mqtt_client_registry import get_ip_for_node, get_iface_for_node
from backend.services.mqtt_traffic_log import get_mqtt_traffic_log
from backend.services.net_interface_resolve import interface_label
from backend.services.node_ip_diagnostics import build_ip_conflict_map, enrich_scan_item
from backend.services.node_utils import get_node_metadata, is_node_placed, is_node_offline, node_category


_STATE_PRIORITY = {
    "active": 0,
    "acknowledged": 1,
    "detected": 2,
    "offline": 3,
    "inactive": 4,
    "decommissioned": 5,
    "manual": 6,
}


def _node_ip(node: WifiNode) -> str | None:
    meta = get_node_metadata(node)
    return meta.get("node_ip") or get_ip_for_node(node.mac_address)


def _commission_state(node: WifiNode) -> str:
    return node_category(node)


def _server_interface(node: WifiNode) -> str | None:
    meta = get_node_metadata(node)
    return meta.get("server_interface") or get_iface_for_node(node.mac_address)


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _pick_iso(values: list[str | None], *, latest: bool) -> str | None:
    stamped = [(v, _parse_dt(v)) for v in values if v]
    stamped = [(raw, dt) for raw, dt in stamped if dt is not None]
    if not stamped:
        return None
    stamped.sort(key=lambda item: item[1], reverse=latest)
    return stamped[0][0]


def _dt_rank(value: str | None) -> float:
    dt = _parse_dt(value)
    return dt.timestamp() if dt is not None else float('-inf')



def _merge_items(items: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        ip = item.get("node_ip") or "--"
        key = f"ip:{ip}" if ip and ip != "--" else f"node:{item.get('mac_address') or item.get('node_id')}"
        grouped.setdefault(key, []).append(item)

    merged: list[dict] = []
    for group in grouped.values():
        if len(group) == 1:
            item = dict(group[0])
            item["logical_node_ids"] = [item.get("node_id")]
            item["logical_mac_addresses"] = [item.get("mac_address")]
            item["logical_strata_ids"] = [item.get("strata_node_id")] if item.get("strata_node_id") else []
            item["logical_count"] = 1
            item["merged_by_ip"] = False
            merged.append(item)
            continue

        ordered = sorted(
            group,
            key=lambda item: (
                _STATE_PRIORITY.get(item.get("commission_state") or "manual", 99),
                -_dt_rank(item.get("last_payload_at") or item.get("last_heard_at") or item.get("first_discovered_at")),
                -(item.get("messages_total") or 0),
                -(item.get("node_id") or 0),
            )
        )
        rep = dict(ordered[0])
        rep["logical_node_ids"] = [item.get("node_id") for item in group if item.get("node_id") is not None]
        rep["logical_mac_addresses"] = [item.get("mac_address") for item in group if item.get("mac_address")]
        rep["logical_strata_ids"] = [item.get("strata_node_id") for item in group if item.get("strata_node_id")]
        rep["logical_count"] = len(group)
        rep["merged_by_ip"] = True
        rep["messages_total"] = sum(int(item.get("messages_total") or 0) for item in group)
        rep["first_discovered_at"] = _pick_iso([item.get("first_discovered_at") for item in group], latest=False)
        rep["last_payload_at"] = _pick_iso([item.get("last_payload_at") for item in group], latest=True)
        rep["last_heard_at"] = _pick_iso([item.get("last_heard_at") for item in group], latest=True)
        rep["last_timestamp"] = rep.get("last_payload_at") or rep.get("last_heard_at") or rep.get("first_discovered_at")
        rep["online"] = any(bool(item.get("online")) for item in group)
        rep["placed_on_map"] = any(bool(item.get("placed_on_map")) for item in group)
        rep["mqtt_acknowledged"] = any(bool(item.get("mqtt_acknowledged")) for item in group)
        rep["clock_skew_warning"] = any(bool(item.get("clock_skew_warning")) for item in group)
        latest_skew = sorted(
            group,
            key=lambda item: _dt_rank(item.get("last_payload_at") or item.get("last_heard_at") or item.get("first_discovered_at")),
            reverse=True,
        )[0]
        rep["last_node_reported_at"] = latest_skew.get("last_node_reported_at")
        rep["last_clock_skew_seconds"] = latest_skew.get("last_clock_skew_seconds")
        rep["clock_skew_warn_seconds"] = latest_skew.get("clock_skew_warn_seconds")
        rep["last_topic"] = latest_skew.get("last_topic") or rep.get("last_topic")
        rep["last_payload"] = latest_skew.get("last_payload") or rep.get("last_payload")
        rep["last_client_id"] = latest_skew.get("last_client_id") or rep.get("last_client_id")
        rep["payload_format"] = latest_skew.get("payload_format") or rep.get("payload_format")

        states = {item.get("commission_state") for item in group}
        for state in ("active", "acknowledged", "detected", "offline", "inactive", "decommissioned", "manual"):
            if state in states:
                rep["commission_state"] = state
                break

        placed = next((item for item in ordered if item.get("placed_on_map")), None)
        if placed is not None:
            rep["pos_x"] = placed.get("pos_x")
            rep["pos_y"] = placed.get("pos_y")
            rep["pos_z"] = placed.get("pos_z")
        name_candidate = next((item.get("name") for item in ordered if item.get("mqtt_acknowledged") and item.get("name")), None)
        if name_candidate:
            rep["name"] = name_candidate
        merged.append(rep)

    merged.sort(
        key=lambda item: (
            _STATE_PRIORITY.get(item.get("commission_state") or "manual", 99),
            _dt_rank(item.get("last_payload_at") or item.get("last_heard_at") or item.get("first_discovered_at")),
            item.get("name") or "",
        ),
        reverse=False,
    )
    return merged



def scan_nodes(session=None) -> dict:
    """Build scan snapshot for commission table (name + IP required columns)."""
    sess = session or db.session
    nodes = sess.query(WifiNode).order_by(WifiNode.last_heartbeat.desc().nullslast(), WifiNode.id.desc()).all()
    nodes = [n for n in nodes if (get_node_metadata(n).get("mqtt_auto_detected") or get_node_metadata(n).get("mqtt_acknowledged") or get_node_metadata(n).get("last_payload_at") or get_node_metadata(n).get("first_discovered_at"))]
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
            "node_ip": ip or "--",
            "client_ip": ip or "--",
            "server_interface": iface or "--",
            "server_interface_label": iface_label or "--",
            "mac_address": n.mac_address,
            "strata_node_id": meta.get("strata_node_id"),
            "first_discovered_at": meta.get("first_discovered_at") or (n.created_at.isoformat() if n.created_at else None),
            "last_payload_at": meta.get("last_payload_at") or meta.get("last_seen_at") or (n.last_heartbeat.isoformat() if n.last_heartbeat else None),
            "last_heard_at": n.last_heartbeat.isoformat() if n.last_heartbeat else None,
            "last_timestamp": meta.get("last_payload_at") or meta.get("last_seen_at") or (n.last_heartbeat.isoformat() if n.last_heartbeat else None),
            "messages_total": meta.get("messages_total"),
            "payload_format": meta.get("payload_format", "unknown"),
            "last_node_reported_at": meta.get("last_node_reported_at"),
            "last_clock_skew_seconds": meta.get("last_clock_skew_seconds"),
            "clock_skew_warning": bool(meta.get("clock_skew_warning")),
            "clock_skew_warn_seconds": meta.get("clock_skew_warn_seconds"),
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
    items = _merge_items(items)
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
        "acknowledged": [],
        "active": [],
        "offline": [],
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
