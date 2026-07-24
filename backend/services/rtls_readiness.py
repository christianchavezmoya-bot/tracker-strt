"""RTLS commissioning readiness — checklist for admin UI."""
from __future__ import annotations

from backend.models.tracker import WifiNode
from backend.services.node_utils import is_node_placed
from backend.services.mqtt_broker_manager import broker_status_summary
from backend.services.positioning_profile import get_positioning_profile

MIN_ANCHORS_FOR_TAGS = 3


def compute_readiness(db_session) -> dict:
    nodes = db_session.query(WifiNode).all()
    placed = [n for n in nodes if is_node_placed(n)]
    discovered = [n for n in nodes if not is_node_placed(n)]
    broker = broker_status_summary()
    profile = get_positioning_profile(db_session)

    anchors_required = int(profile.get("min_anchors") or MIN_ANCHORS_FOR_TAGS)
    anchors_needed = max(0, anchors_required - len(placed))
    broker_ok = bool(broker.get("enabled") and broker.get("running"))
    tags_visible = broker_ok and len(placed) >= anchors_required

    checklist = [
        {
            "id": "broker",
            "label": "Receiving data from WiFi nodes",
            "ok": broker_ok,
            "hint": "Turn on the MQTT receiver in Settings → Network & MQTT"
            if not broker_ok
            else f"Listening on port {broker.get('port', 1883)}",
        },
        {
            "id": "nodes_detected",
            "label": f"{len(nodes)} node(s) detected",
            "ok": len(nodes) > 0,
            "hint": "Power on WiFi units and point them to this server's address"
            if not nodes
            else "Nodes are sending data or registered manually",
        },
        {
            "id": "anchors_placed",
            "label": f"{len(placed)} of {anchors_required} anchors placed on map",
            "ok": len(placed) >= anchors_required,
            "hint": f"Place {anchors_needed} more anchor(s) using Map Setup"
            if anchors_needed
            else f"Enough anchors for {profile.get('label', 'active').lower()} positioning",
        },
        {
            "id": "tags_live",
            "label": "Tags visible on Live Map",
            "ok": tags_visible,
            "hint": "Complete the steps above to see moving tags"
            if not tags_visible
            else "System is tracking tags",
        },
    ]

    done = sum(1 for item in checklist if item["ok"])
    return {
        "ready": tags_visible,
        "progress_pct": int(round(100 * done / max(len(checklist), 1))),
        "anchors_placed": len(placed),
        "anchors_required": anchors_required,
        "positioning_profile": profile,
        "anchors_needed": anchors_needed,
        "nodes_total": len(nodes),
        "nodes_discovered": len(discovered),
        "tags_visible": tags_visible,
        "broker": broker,
        "checklist": checklist,
    }
