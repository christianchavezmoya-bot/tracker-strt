"""Merge multiple STRATA logical IDs that share one physical unit IP."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from backend.extensions import db
from backend.models.tracker import WifiNode
from backend.services.mqtt_client_registry import get_ip_for_node, normalize_client_ip
from backend.services.node_utils import get_node_metadata

logger = logging.getLogger(__name__)

_STATE_PRIORITY = {
    "active": 0,
    "acknowledged": 1,
    "detected": 2,
    "offline": 3,
    "inactive": 4,
    "decommissioned": 5,
    "manual": 6,
}


def normalize_anchor_ip(ip: str | None) -> str | None:
    return normalize_client_ip(ip)


def _node_ip_value(node: WifiNode) -> str | None:
    meta = get_node_metadata(node)
    return normalize_anchor_ip(
        meta.get("node_ip") or meta.get("physical_unit_ip") or get_ip_for_node(node.mac_address)
    )


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _node_rank(node: WifiNode) -> tuple:
    from backend.services.node_utils import node_category

    meta = get_node_metadata(node)
    state = node_category(node)
    last = meta.get("last_payload_at") or meta.get("last_seen_at")
    dt = _parse_dt(last)
    ts = dt.timestamp() if dt is not None else float("-inf")
    return (
        _STATE_PRIORITY.get(state, 99),
        -ts,
        -(int(meta.get("messages_total") or 0)),
        (node.id or 0),
    )


def find_canonical_node_for_ip(ip: str | None, session=None) -> WifiNode | None:
    """Best existing anchor row for a physical unit IP (excludes merged aliases)."""
    ip = normalize_anchor_ip(ip)
    if not ip:
        return None
    sess = session or db.session
    candidates: list[WifiNode] = []
    for node in sess.query(WifiNode).all():
        meta = get_node_metadata(node)
        if meta.get("merged_into"):
            continue
        if _node_ip_value(node) == ip:
            candidates.append(node)
    if not candidates:
        return None
    return sorted(candidates, key=_node_rank)[0]


def record_strata_alias(
    canonical: WifiNode,
    alias_key: str,
    strata_id: str | None = None,
) -> None:
    """Track logical STRATA IDs merged into one physical anchor."""
    alias_key = (alias_key or "").upper()
    if not alias_key or alias_key == (canonical.mac_address or "").upper():
        return
    meta = get_node_metadata(canonical)
    aliases = [a.upper() for a in meta.get("merged_mac_addresses") or []]
    strata_ids = [str(s) for s in meta.get("merged_strata_ids") or []]
    if alias_key not in aliases:
        aliases.append(alias_key)
    if strata_id and str(strata_id) not in strata_ids:
        strata_ids.append(str(strata_id))
    if not meta.get("canonical_strata_id") and strata_id:
        meta["canonical_strata_id"] = str(strata_id)
    meta["merged_mac_addresses"] = aliases
    meta["merged_strata_ids"] = strata_ids
    meta["physical_unit_ip"] = meta.get("physical_unit_ip") or meta.get("node_ip")
    canonical.metadata_json = json.dumps(meta)


def resolve_canonical_node_key(
    node_key: str,
    *,
    client_ip: str | None = None,
    session=None,
) -> tuple[str, WifiNode | None]:
    """
    When several STRATA IDs share one IP, route ingest to the canonical anchor row.
    Returns (effective_key, canonical_node_or_none).
    """
    key = (node_key or "").upper()
    ip = normalize_anchor_ip(client_ip)
    if not key.startswith("STRATA:") or not ip:
        return key, None
    canonical = find_canonical_node_for_ip(ip, session=session)
    if not canonical:
        return key, None
    canonical_key = (canonical.mac_address or "").upper()
    if canonical_key == key:
        return key, canonical
    return canonical_key, canonical


def consolidate_duplicate_ip_nodes(session=None) -> int:
    """
    Mark duplicate DB rows that share one client IP as merged into a canonical anchor.
    Returns number of rows marked merged.
    """
    sess = session or db.session
    by_ip: dict[str, list[WifiNode]] = {}
    for node in sess.query(WifiNode).all():
        meta = get_node_metadata(node)
        if meta.get("merged_into"):
            continue
        ip = _node_ip_value(node)
        if not ip:
            continue
        by_ip.setdefault(ip, []).append(node)

    merged_count = 0
    for ip, group in by_ip.items():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=_node_rank)
        canonical = ordered[0]
        canonical_meta = get_node_metadata(canonical)
        canonical_meta.setdefault("physical_unit_ip", ip)
        canonical.metadata_json = json.dumps(canonical_meta)
        for duplicate in ordered[1:]:
            dup_meta = get_node_metadata(duplicate)
            if dup_meta.get("merged_into"):
                continue
            record_strata_alias(
                canonical,
                duplicate.mac_address,
                dup_meta.get("strata_node_id"),
            )
            dup_meta["merged_into"] = canonical.id
            dup_meta["merged_into_mac"] = canonical.mac_address
            dup_meta["physical_unit_ip"] = ip
            duplicate.metadata_json = json.dumps(dup_meta)
            merged_count += 1
            logger.info(
                "Merged duplicate anchor %s into %s (IP %s)",
                duplicate.mac_address,
                canonical.mac_address,
                ip,
            )
        canonical.metadata_json = json.dumps(get_node_metadata(canonical))
    if merged_count:
        try:
            sess.commit()
        except Exception:
            sess.rollback()
            raise
    return merged_count
