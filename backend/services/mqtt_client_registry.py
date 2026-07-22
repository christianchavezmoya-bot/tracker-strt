"""Map MQTT client_id → remote IP (from broker CONNECT)."""
from __future__ import annotations

import threading
from typing import Optional

_lock = threading.Lock()
_by_client: dict[str, str] = {}
_by_node_key: dict[str, str] = {}


def register_client(client_id: str, remote_address: str | None) -> None:
    if not client_id or not remote_address:
        return
    ip = str(remote_address).split("%")[0]
    with _lock:
        _by_client[client_id] = ip


def link_node_key(node_key: str, client_id: str) -> None:
    if not node_key or not client_id:
        return
    with _lock:
        ip = _by_client.get(client_id)
        if ip:
            _by_node_key[node_key.upper()] = ip


def get_ip_for_client(client_id: str) -> Optional[str]:
    with _lock:
        return _by_client.get(client_id or "")


def get_ip_for_node(node_key: str) -> Optional[str]:
    with _lock:
        return _by_node_key.get((node_key or "").upper())
