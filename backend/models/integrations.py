"""Webhooks and scheduled report delivery models."""
from datetime import datetime, timezone
from backend.extensions import db


class WebhookEndpoint(db.Model):
    __tablename__ = "webhook_endpoints"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    url        = db.Column(db.String(500), nullable=False)
    events     = db.Column(db.Text, nullable=True)   # JSON list e.g. ["alert.created","zone.enter"]
    secret     = db.Column(db.String(120), nullable=True)
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_delivery_at = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(40), nullable=True)

    def to_dict(self) -> dict:
        import json
        ev = []
        if self.events:
            try:
                ev = json.loads(self.events)
            except Exception:
                ev = []
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "events": ev,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_delivery_at": self.last_delivery_at.isoformat() if self.last_delivery_at else None,
            "last_status": self.last_status,
        }


class ReportSchedule(db.Model):
    __tablename__ = "report_schedules"

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(120), nullable=False)
    report_type  = db.Column(db.String(40), default="summary")  # summary|dwell|battery|full
    cron         = db.Column(db.String(40), default="0 6 * * *")  # daily 06:00
    recipients   = db.Column(db.Text, nullable=True)  # comma-separated emails
    format       = db.Column(db.String(10), default="csv")  # csv|pdf
    is_active    = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_run_at  = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "report_type": self.report_type,
            "cron": self.cron,
            "recipients": self.recipients,
            "format": self.format,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
        }
