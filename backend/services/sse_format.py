"""SSE message formatting helpers."""
from __future__ import annotations

import json
from typing import Any


def format_sse_event(data: dict[str, Any]) -> str:
    """Format payload as SSE with named event line (required for EventSource listeners)."""
    event_type = data.get("type") or "message"
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
