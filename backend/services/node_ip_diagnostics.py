"""IP conflict detection and node connection diagnostics."""
from __future__ import annotations

from backend.services.mqtt_client_registry import get_ip_for_node, get_iface_for_node
from backend.services.node_utils import get_node_metadata


def build_ip_conflict_map(items: list[dict]) -> dict[str, list[str]]:
    """Map IP → node keys when multiple anchors share the same client IP."""
    by_ip: dict[str, list[str]] = {}
    for item in items:
        if item.get("merged_by_ip") or (item.get("logical_count") or 1) > 1:
            continue
        ip = item.get("node_ip") or item.get("client_ip")
        if not ip or ip in ("—", "--"):
            continue
        by_ip.setdefault(ip, []).append(item.get("mac_address") or str(item.get("node_id")))
    return {ip: keys for ip, keys in by_ip.items() if len(keys) > 1}


def enrich_scan_item(item: dict, conflicts: dict[str, list[str]]) -> dict:
    ip = item.get("node_ip") or "—"
    mac = item.get("mac_address") or ""
    shared = conflicts.get(ip, []) if ip != "—" else []
    item["ip_conflict"] = len(shared) > 1
    item["ip_shared_with"] = [k for k in shared if k != mac] if item["ip_conflict"] else []
    return item


def node_connection_fields(node) -> dict:
    meta = get_node_metadata(node)
    ip = meta.get("node_ip") or get_ip_for_node(node.mac_address)
    iface = meta.get("server_interface") or get_iface_for_node(node.mac_address)
    return {
        "node_ip": ip or "—",
        "server_interface": iface or "—",
        "server_interface_label": meta.get("server_interface_label") or iface or "—",
    }
