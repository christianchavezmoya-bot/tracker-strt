"""Tests for SSE message formatting."""
import json

from backend.services.sse_format import format_sse_event


def test_format_sse_event_includes_event_line():
    msg = format_sse_event({"type": "position_update", "tracker_id": 1, "x": 1.0})
    assert msg.startswith("event: position_update\n")
    assert "data:" in msg
    payload = json.loads(msg.split("data:", 1)[1].strip())
    assert payload["tracker_id"] == 1


def test_format_sse_batch_event():
    msg = format_sse_event({"type": "batch", "updates": [{"tracker_id": 1}]})
    assert "event: batch\n" in msg
    payload = json.loads(msg.split("data:", 1)[1].strip())
    assert len(payload["updates"]) == 1
