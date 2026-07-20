"""Presence timeline helpers for tracker chart view."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.models import Tracker, TrackerAckStatus
from backend.models.positioning import TrackerPresenceLog


def get_presence_timeline(minutes: int = 60, tracker_ids: list[int] | None = None) -> dict:
    minutes = max(1, min(1440, int(minutes)))
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes)

    q = Tracker.query
    if tracker_ids:
        q = q.filter(Tracker.id.in_(tracker_ids))
    else:
        q = q.filter(Tracker.ack_status != int(TrackerAckStatus.UNACKNOWLEDGED))
    trackers = q.order_by(Tracker.id).limit(50).all()

    out = []
    for t in trackers:
        logs = (
            TrackerPresenceLog.query
            .filter(TrackerPresenceLog.tracker_id == t.id, TrackerPresenceLog.timestamp >= since)
            .order_by(TrackerPresenceLog.timestamp.asc())
            .all()
        )
        label = t.nickname or t.assigned_name or t.hardware_id
        if t.device_model:
            label = f"{label} · {t.device_model}"
        out.append({
            "id": t.id,
            "hardware_id": t.hardware_id,
            "label": label,
            "last_seen_at": (
                datetime.fromtimestamp(t.last_report_time, tz=timezone.utc).isoformat()
                if t.last_report_time else None
            ),
            "samples": [s.to_dict() for s in logs],
        })

    return {
        "window_minutes": minutes,
        "since": since.isoformat() + "Z",
        "trackers": out,
    }
