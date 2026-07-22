"""Log anchor/node MQTT presence for timeline charts."""
from __future__ import annotations

from datetime import datetime, timedelta

from backend.extensions import db
from backend.models.positioning import NodePresenceLog
from backend.models.tracker import WifiNode
from backend.services.mqtt_client_registry import get_ip_for_node
from backend.services.node_utils import get_node_metadata


def log_node_presence(
    node: WifiNode,
    *,
    online: bool = True,
    rssi: float | None = None,
    node_ip: str | None = None,
) -> None:
    """Append presence sample (throttled to ~1/min per node)."""
    cutoff = datetime.utcnow() - timedelta(seconds=55)
    recent = (
        db.session.query(NodePresenceLog)
        .filter(NodePresenceLog.node_id == node.id, NodePresenceLog.timestamp >= cutoff)
        .first()
    )
    ip = node_ip or get_node_metadata(node).get("node_ip") or get_ip_for_node(node.mac_address)
    if recent and recent.online == online and (rssi is None or recent.rssi == rssi):
        if ip and recent.node_ip != ip:
            recent.node_ip = ip
        return
    db.session.add(
        NodePresenceLog(
            node_id=node.id,
            online=online,
            rssi=rssi,
            node_ip=ip,
        )
    )


def update_node_connection_metadata(
    node: WifiNode,
    *,
    ip: str | None = None,
    server_interface: str | None = None,
    server_interface_label: str | None = None,
) -> None:
    import json
    meta = get_node_metadata(node)
    changed = False
    if ip and meta.get("node_ip") != ip:
        meta["node_ip"] = ip
        changed = True
    if server_interface and meta.get("server_interface") != server_interface:
        meta["server_interface"] = server_interface
        changed = True
    if server_interface_label and meta.get("server_interface_label") != server_interface_label:
        meta["server_interface_label"] = server_interface_label
        changed = True
    if changed:
        node.metadata_json = json.dumps(meta)


def update_node_ip_metadata(node: WifiNode, ip: str | None) -> None:
    update_node_connection_metadata(node, ip=ip)
