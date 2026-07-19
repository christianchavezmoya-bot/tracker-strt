"""Scheduler service — scheduled backups + email reports."""
from __future__ import annotations
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
_scheduler = None


def init_scheduler(app):
    """Start APScheduler jobs inside the Flask app."""
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("APScheduler not installed — scheduled jobs disabled")
        return None

    if _scheduler is not None:
        return _scheduler

    sched = BackgroundScheduler(daemon=True)

    def _run_scheduled_backup():
        with app.app_context():
            try:
                from backend.api.backup import _create_backup_file
                _create_backup_file(trigger="scheduled", user_id=None)
                logger.info("Scheduled backup completed")
            except Exception as e:
                logger.error("Scheduled backup failed: %s", e)

    def _run_scheduled_reports():
        with app.app_context():
            try:
                from backend.services.report_delivery import deliver_due_schedules
                deliver_due_schedules()
            except Exception as e:
                logger.error("Scheduled reports failed: %s", e)

    # Daily backup at 02:30 UTC
    sched.add_job(_run_scheduled_backup, "cron", hour=2, minute=30, id="daily_backup", replace_existing=True)
    # Check report schedules every hour
    sched.add_job(_run_scheduled_reports, "interval", hours=1, id="report_schedules", replace_existing=True)

    sched.start()
    _scheduler = sched
    logger.info("APScheduler started (daily backup + hourly report check)")
    return sched


def get_scheduler():
    return _scheduler
