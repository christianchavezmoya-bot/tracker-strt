"""SSE stream soak tests — short CI gate + optional long-run validation."""
import json
import os
import time


def _read_sse_events(client, headers, max_seconds: float, min_chunks: int = 2):
    """Read SSE iterator until min_chunks received or max_seconds elapsed."""
    chunks = []
    deadline = time.monotonic() + max_seconds
    with client.get("/api/stream/positions", headers=headers) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in (resp.content_type or "")
        stream = iter(resp.response)
        while time.monotonic() < deadline and len(chunks) < min_chunks:
            try:
                chunk = next(stream)
                if chunk:
                    chunks.append(chunk)
            except StopIteration:
                break
    return chunks


def _chunks_to_events(chunks) -> list[str]:
    text = b"".join(chunks).decode("utf-8", errors="replace")
    return [b.strip() for b in text.split("\n\n") if b.strip()]


def _parse_event_type(block: str) -> str | None:
    for line in block.splitlines():
        if line.startswith("event:"):
            return line.split(":", 1)[1].strip()
        if line.startswith("data:"):
            try:
                payload = json.loads(line.split(":", 1)[1].strip())
                if payload.get("type") == "heartbeat":
                    return "heartbeat"
            except json.JSONDecodeError:
                pass
            return "data"
    return None


def test_stream_status_endpoint(client, admin_headers):
    res = client.get("/api/stream/status", headers=admin_headers)
    assert res.status_code == 200
    data = res.get_json() or {}
    assert "ingestion_running" in data
    assert "sse_clients" in data
    assert "timestamp" in data


def test_sse_snapshot_event_format():
    from backend.api.stream import _snapshot_event

    event = _snapshot_event()
    assert "event:" in event or "data:" in event


def test_sse_snapshot_and_heartbeat(client, admin_headers):
    """CI soak: stream opens and delivers snapshot (+ heartbeat when idle)."""
    duration = float(os.getenv("SSE_SOAK_SECONDS", "35"))
    chunks = _read_sse_events(client, admin_headers, max_seconds=duration, min_chunks=1)
    assert chunks, "SSE stream returned no data"
    events = _chunks_to_events(chunks)
    types = {_parse_event_type(e) for e in events}
    assert "snapshot" in types or "data" in types or "heartbeat" in types


def test_sse_no_disconnect_under_load(client, admin_headers):
    """Verify multiple sequential SSE connections succeed (reconnect resilience)."""
    for _ in range(3):
        chunks = _read_sse_events(client, admin_headers, max_seconds=8, min_chunks=1)
        assert chunks
