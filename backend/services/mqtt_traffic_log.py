"""In-memory ring buffer of raw MQTT messages for diagnostics."""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class MqttTrafficEntry:
    at: datetime
    client_id: str
    topic: str
    payload: str
    node_key: Optional[str] = None
    node_id: Optional[int] = None
    parsed: bool = False
    parse_count: int = 0
    payload_format: str = "unknown"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["at"] = self.at.isoformat()
        d["payload_preview"] = (self.payload or "")[:240]
        return d


class MqttTrafficLog:
    """Thread-safe recent MQTT message log (not persisted to DB)."""

    def __init__(self, maxlen: int = 500):
        self._maxlen = maxlen
        self._entries: deque[MqttTrafficEntry] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self.total_received = 0

    def append(
        self,
        *,
        client_id: str,
        topic: str,
        payload: str,
        node_key: str | None = None,
        node_id: int | None = None,
        parsed: bool = False,
        parse_count: int = 0,
        payload_format: str = "unknown",
    ) -> MqttTrafficEntry:
        entry = MqttTrafficEntry(
            at=datetime.utcnow(),
            client_id=client_id or "",
            topic=topic or "",
            payload=(payload or "")[:2000],
            node_key=node_key,
            node_id=node_id,
            parsed=parsed,
            parse_count=parse_count,
            payload_format=payload_format,
        )
        with self._lock:
            self.total_received += 1
            self._entries.appendleft(entry)
        return entry

    def list_entries(
        self,
        *,
        limit: int = 100,
        node_key: str | None = None,
        node_id: int | None = None,
    ) -> list[dict]:
        limit = max(1, min(int(limit or 100), 500))
        key = (node_key or "").upper()
        with self._lock:
            items = list(self._entries)
        if node_id is not None:
            items = [e for e in items if e.node_id == node_id]
        elif key:
            items = [e for e in items if (e.node_key or "").upper() == key]
        return [e.to_dict() for e in items[:limit]]

    def summary(self) -> dict:
        with self._lock:
            recent = list(self._entries)[:200]
            total = self.total_received
        formats: dict[str, int] = {}
        parsed_n = 0
        for e in recent:
            formats[e.payload_format] = formats.get(e.payload_format, 0) + 1
            if e.parsed:
                parsed_n += 1
        return {
            "total_received": total,
            "buffer_size": len(recent),
            "recent_parsed": parsed_n,
            "recent_unparsed": len(recent) - parsed_n,
            "payload_formats": formats,
        }


_traffic_log: Optional[MqttTrafficLog] = None


def get_mqtt_traffic_log() -> MqttTrafficLog:
    global _traffic_log
    if _traffic_log is None:
        _traffic_log = MqttTrafficLog()
    return _traffic_log
