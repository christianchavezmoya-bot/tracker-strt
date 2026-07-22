"""Map MQTT client_id → remote IP (from broker CONNECT / PUBLISH)."""
from __future__ import annotations

import re
import threading
from typing import Optional

_lock = threading.Lock()
_by_client: dict[str, str] = {}
_by_node_key: dict[str, str] = {}


def _normalize_ip(remote_address: str | None) -> str | None:
    if not remote_address:
        return None
    raw = str(remote_address).strip()
    if not raw:
        return None
    # Strip IPv6 zone id (fe80::1%eth0)
    raw = raw.split("%")[0]
    # Handle ("10.60.1.5", 54321) style strings
    m = re.match(r"^\('?([\d.]+)'?,\s*\d+\)$", raw)
    if m:
        return m.group(1)
    # host:port
    if raw.count(":") == 1 and raw.split(":")[0].replace(".", "").isdigit():
        return raw.split(":")[0]
    return raw


def normalize_client_ip(remote_address: str | None) -> str | None:
    return _normalize_ip(remote_address)


def register_client(client_id: str, remote_address: str | None) -> None:
    ip = _normalize_ip(remote_address)
    if not client_id or not ip:
        return
    with _lock:
        _by_client[client_id] = ip


def link_node_key(node_key: str, client_id: str, *, client_ip: str | None = None) -> None:
    if not node_key:
        return
    ip = _normalize_ip(client_ip)
    with _lock:
        if not ip and client_id:
            ip = _by_client.get(client_id)
        if ip:
            _by_node_key[node_key.upper()] = ip


def note_node_ip(node_key: str, client_ip: str | None) -> None:
    ip = _normalize_ip(client_ip)
    if not node_key or not ip:
        return
    with _lock:
        _by_node_key[node_key.upper()] = ip


def get_ip_for_client(client_id: str) -> Optional[str]:
    with _lock:
        return _by_client.get(client_id or "")


def get_ip_for_node(node_key: str) -> Optional[str]:
    with _lock:
        return _by_node_key.get((node_key or "").upper())
