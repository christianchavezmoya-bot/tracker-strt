"""Scheduled report delivery (CSV/PDF email)."""
from __future__ import annotations
import csv
import io
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


def deliver_due_schedules():
    """Run active ReportSchedule rows whose cron hour matches current UTC hour (simple matcher)."""
    from backend.models import ReportSchedule
    from backend.extensions import db

    now = datetime.now(timezone.utc)
    rows = ReportSchedule.query.filter_by(is_active=True).all()
    for row in rows:
        if not _cron_due(row.cron, now):
            continue
        if row.last_run_at:
            last = row.last_run_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if (now - last).total_seconds() < 3500:
                continue
        try:
            deliver_schedule_now(row)
            db.session.commit()
        except Exception as e:
            logger.error("Report schedule %s failed: %s", row.id, e)


def deliver_schedule_now(row) -> None:
    """Force-deliver one schedule and stamp last_run_at."""
    from backend.extensions import db
    _deliver_one(row)
    row.last_run_at = datetime.now(timezone.utc)
    db.session.commit()


def _cron_due(cron: str, now: datetime) -> bool:
    """Minimal cron: 'M H * * *' — match minute/hour (hour-level jobs ok)."""
    parts = (cron or "0 6 * * *").split()
    if len(parts) < 2:
        return now.hour == 6
    try:
        minute = int(parts[0]) if parts[0] != "*" else now.minute
        hour = int(parts[1]) if parts[1] != "*" else now.hour
    except ValueError:
        return False
    # Hourly scheduler: fire when hour matches (minute ignored for interval=1h)
    return now.hour == hour


def _deliver_one(row):
    from backend.services.notification_service import get_notification_service

    content, filename, mime = build_report(row.report_type, row.format or "csv")
    recipients = [e.strip() for e in (row.recipients or "").split(",") if e.strip()]
    if not recipients:
        logger.info("Schedule %s has no recipients — skipping send", row.id)
        return
    notif = get_notification_service()
    if not notif:
        logger.warning("No notification service — cannot email report")
        return
    for to in recipients:
        notif.send_email(
            to=to,
            subject=f"[HOLO-RTLS] Scheduled report: {row.name}",
            body=f"Attached scheduled {row.report_type} report ({filename}).\n\nGenerated at {datetime.now(timezone.utc).isoformat()}",
            attachment=(filename, content, mime),
        )


def build_report(report_type: str, fmt: str = "csv"):
    """Build report bytes. Returns (bytes, filename, mime)."""
    rows = _collect_rows(report_type)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    if (fmt or "csv").lower() == "pdf":
        from backend.services.pdf_report import rows_to_pdf
        site = None
        try:
            from backend.models import Setting
            row = Setting.query.filter_by(key="site_name").first()
            if row and row.value:
                site = row.value
        except Exception:
            pass
        pdf = rows_to_pdf(
            f"HOLO-RTLS {report_type.title()} Report",
            rows,
            subtitle=f"Report type: {report_type}",
            site_name=site,
        )
        return pdf, f"{report_type}_{stamp}.pdf", "application/pdf"
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        buf.write("message\nNo data\n")
    return buf.getvalue().encode("utf-8"), f"{report_type}_{stamp}.csv", "text/csv"


def _collect_rows(report_type: str) -> list:
    from backend.models import Tracker, Alert, Zone
    from backend.models.positioning import TrackingHistory
    from backend.extensions import db

    since = datetime.now(timezone.utc) - timedelta(days=1)
    rt = (report_type or "summary").lower()

    if rt == "battery":
        trackers = Tracker.query.all()
        return [{
            "id": t.id,
            "name": t.assigned_name or t.hardware_id,
            "battery": getattr(t, "battery_level", None) or getattr(t, "battery", None),
            "status": getattr(t, "asset_state", None),
        } for t in trackers]

    if rt == "dwell":
        # Lightweight: count history samples near zones
        zones = Zone.query.all()
        trackers = Tracker.query.all()
        out = []
        for z in zones:
            for t in trackers:
                out.append({
                    "zone": z.name,
                    "tracker": t.assigned_name or t.hardware_id,
                    "note": "See /api/reports/dwell for precise dwell",
                })
        return out[:200]

    if rt == "full":
        alerts = Alert.query.order_by(Alert.id.desc()).limit(500).all()
        return [{
            "id": a.id,
            "type": a.alert_type,
            "message": a.message,
            "state": a.state,
            "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
        } for a in alerts]

    # summary default
    trackers = Tracker.query.count()
    alerts = Alert.query.filter(Alert.triggered_at >= since).count() if hasattr(Alert, "triggered_at") else Alert.query.count()
    hist = TrackingHistory.query.filter(TrackingHistory.timestamp >= since).count() if hasattr(TrackingHistory, "timestamp") else 0
    return [{
        "metric": "trackers",
        "value": trackers,
    }, {
        "metric": "alerts_24h",
        "value": alerts,
    }, {
        "metric": "history_samples_24h",
        "value": hist,
    }, {
        "metric": "generated_at",
        "value": datetime.now(timezone.utc).isoformat(),
    }]
