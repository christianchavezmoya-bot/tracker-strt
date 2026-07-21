"""Keep WifiNode and WifiAnchor rows in sync for MQTT-discovered nodes."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from backend.extensions import db
from backend.models.detection import WifiAnchor, AnchorStatus
from backend.models.tracker import WifiNode, NodeStatus

logger = logging.getLogger(__name__)


def ensure_wifi_anchor(mac: str, *, name: str | None = None) -> WifiAnchor:
    """Return existing scanner anchor or create a provisional row."""
    mac = mac.upper()
    anchor = db.session.query(WifiAnchor).filter_by(mac_address=mac).first()
    if anchor:
        return anchor
    anchor = WifiAnchor(
        mac_address=mac,
        name=name or f"Node-{mac[-8:]}",
        status=int(AnchorStatus.CALIBRATING),
    )
    db.session.add(anchor)
    db.session.flush()
    logger.info("Auto-registered WifiAnchor %s", mac)
    return anchor


def ensure_wifi_node(mac: str, *, name: str | None = None) -> WifiNode:
    """Return existing WifiNode or create a provisional row for map placement."""
    mac = mac.upper()
    node = db.session.query(WifiNode).filter_by(mac_address=mac).first()
    if node:
        return node
    node = WifiNode(
        mac_address=mac,
        assigned_name=name or f"Node-{mac[-8:]}",
        status=int(NodeStatus.CALIBRATING),
        pos_x=0.0,
        pos_y=0.0,
        pos_z=0.0,
        metadata_json=json.dumps({"placed_on_map": False, "source": "mqtt_auto"}),
    )
    db.session.add(node)
    db.session.flush()
    logger.info("Auto-registered WifiNode %s", mac)
    return node


def touch_node_heartbeat(mac: str) -> None:
    """Update last_seen / heartbeat for both anchor models."""
    mac = mac.upper()
    now = datetime.utcnow()
    anchor = db.session.query(WifiAnchor).filter_by(mac_address=mac).first()
    if anchor:
        anchor.last_seen = now
    node = db.session.query(WifiNode).filter_by(mac_address=mac).first()
    if node:
        node.last_heartbeat = now
        if node.status == int(NodeStatus.OFFLINE):
            node.status = int(NodeStatus.CALIBRATING)


def sync_anchor_position_from_node(node: WifiNode, anchor: WifiAnchor) -> None:
    """Copy calibrated map coordinates from WifiNode to WifiAnchor when set."""
    if node.assigned_name:
        anchor.name = node.assigned_name
    if node.pos_x or node.pos_y:
        anchor.real_x = float(node.pos_x)
        anchor.real_y = float(node.pos_y)
        anchor.real_z = float(node.pos_z or 0.0)
        if anchor.status == int(AnchorStatus.CALIBRATING) and (node.pos_x or node.pos_y):
            anchor.status = int(AnchorStatus.ACTIVE)


def sync_node_full(node: WifiNode) -> WifiAnchor:
    """Sync WifiNode fields to matching WifiAnchor (create if needed)."""
    anchor = ensure_wifi_anchor(node.mac_address, name=node.assigned_name)
    sync_anchor_position_from_node(node, anchor)
    return anchor


def delete_anchor_for_node(mac: str) -> None:
    """Remove scanner anchor row when WifiNode is deleted."""
    from backend.models.detection import DetectionEvent

    mac = mac.upper()
    anchor = db.session.query(WifiAnchor).filter_by(mac_address=mac).first()
    if not anchor:
        return
    db.session.query(DetectionEvent).filter_by(anchor_id=anchor.id).delete()
    db.session.delete(anchor)


def count_placed_nodes(session=None) -> int:
    from backend.services.node_utils import is_node_placed

    sess = session or db.session
    nodes = sess.query(WifiNode).all()
    return sum(1 for n in nodes if is_node_placed(n))


def refresh_tag_positions(session=None) -> dict:
    """Recompute RSSI positions and push to Live Map via SSE."""
    from backend.services.wifi_positioning import WifiPositioningService

    sess = session or db.session
    pos_svc = WifiPositioningService(sess)
    fixes = pos_svc.compute_all_positions()
    if fixes:
        from backend.api.scanner import _sync_scanner_fixes_to_core
        _sync_scanner_fixes_to_core(fixes)
    else:
        sess.commit()
    return {
        "positions_computed": len(fixes or []),
        "anchors_placed": count_placed_nodes(sess),
    }


def ensure_node_pair(mac: str) -> tuple[WifiNode, WifiAnchor]:
    """Ensure both anchor tables have a row for this node MAC."""
    mac = mac.upper()
    node = ensure_wifi_node(mac)
    anchor = ensure_wifi_anchor(mac, name=node.assigned_name)
    sync_anchor_position_from_node(node, anchor)
    return node, anchor
