"""Shared helpers for WifiNode placement and filtering."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from backend.models.tracker import WifiNode, NodeStatus


def get_node_metadata(node: WifiNode) -> dict:
    if not node.metadata_json:
        return {}
    try:
        data = json.loads(node.metadata_json)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def is_node_placed(node: WifiNode) -> bool:
    meta = get_node_metadata(node)
    if meta.get("placed_on_map") is True:
        return True
    if meta.get("placed_on_map") is False:
        return False
    x = float(node.pos_x or 0)
    y = float(node.pos_y or 0)
    return x != 0 or y != 0


def mark_node_placed(node: WifiNode) -> None:
    meta = get_node_metadata(node)
    meta["placed_on_map"] = True
    node.metadata_json = json.dumps(meta)
    if node.status == int(NodeStatus.CALIBRATING):
        node.status = int(NodeStatus.ACTIVE)


def node_category(node: WifiNode, offline_seconds: float = 120.0) -> str:
    """Return discovered | placed | offline for UI tabs."""
    if is_node_offline(node, offline_seconds):
        return "offline"
    if is_node_placed(node):
        return "placed"
    return "discovered"


def is_node_offline(node: WifiNode, offline_seconds: float = 120.0) -> bool:
    if node.status == int(NodeStatus.OFFLINE):
        return True
    if not node.last_heartbeat:
        return False
    cutoff = datetime.utcnow() - timedelta(seconds=offline_seconds)
    hb = node.last_heartbeat
    if hb.tzinfo is not None:
        hb = hb.replace(tzinfo=None)
    return hb < cutoff
