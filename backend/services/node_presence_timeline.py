"""Presence timeline for anchor/node health charts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.models.positioning import NodePresenceLog
from backend.models.tracker import WifiNode
from backend.services.node_utils import get_node_metadata, is_node_offline


def get_node_presence_timeline(minutes: int = 60, node_ids: list[int] | None = None) -> dict:
    minutes = max(1, min(1440, int(minutes)))
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes)

    q = WifiNode.query
    if node_ids:
        q = q.filter(WifiNode.id.in_(node_ids))
    nodes = q.order_by(WifiNode.id).limit(80).all()

    out = []
    for n in nodes:
        logs = (
            NodePresenceLog.query
            .filter(NodePresenceLog.node_id == n.id, NodePresenceLog.timestamp >= since)
            .order_by(NodePresenceLog.timestamp.asc())
            .all()
        )
        meta = get_node_metadata(n)
        label = n.assigned_name or meta.get("strata_node_id") or n.mac_address
        ip = meta.get("node_ip") or (logs[-1].node_ip if logs else None)
        out.append({
            "id": n.id,
            "mac_address": n.mac_address,
            "label": label,
            "node_ip": ip,
            "online": not is_node_offline(n),
            "last_heard_at": n.last_heartbeat.isoformat() if n.last_heartbeat else None,
            "samples": [s.to_dict() for s in logs],
        })

    return {
        "window_minutes": minutes,
        "since": since.isoformat() + "Z",
        "nodes": out,
    }
