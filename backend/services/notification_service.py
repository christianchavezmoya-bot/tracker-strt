"""
HOLO-RTLS — Notification Service
Handles dispatch of alerts and system notifications:
  - In-app: write to Notification DB table (polled via SSE)
  - Email: via SMTP (Flask-Mail)
  - SMS: via Twilio (configurable)
"""
from __future__ import annotations
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
from datetime import datetime, timezone

from flask import Flask
from flask_mail import Mail, Message

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Multi-channel notification dispatcher.
    Reads SMTP/Twilio config from backend.config and Setting table.
    """

    def __init__(self, db_session, app: Flask = None):
        self._db = db_session
        self._app = app
        self._mail: Optional[Mail] = None
        self._twilio_client = None
        self._email_enabled = False
        self._sms_enabled = False

        if app:
            self._init_mail(app)

    def _init_mail(self, app: Flask):
        try:
            self._mail = Mail(app)
            self._email_enabled = bool(app.config.get("MAIL_SERVER"))
            logger.info(f"Email notifications: {'enabled' if self._email_enabled else 'disabled'}")
        except Exception as e:
            logger.warning(f"Mail not initialised: {e}")

    # ── In-app notifications ───────────────────────────────────────────────────

    def notify_alert(self, alert, recipient_ids: List[int] = None):
        """
        Create in-app notifications for all relevant users.
        Also triggers email/SMS based on user preferences.
        """
        with self._app.app_context():
            from backend.models import Notification, NotificationType, User
            from backend.extensions import db

            # Determine recipients: all operators + admins, or specific users
            if recipient_ids:
                users = self._db.query(User).filter(User.id.in_(recipient_ids)).all()
            else:
                # All active operators and admins get alerts
                from backend.models import UserRole
                users = self._db.query(User).filter(
                    User.is_active == True,
                    User.role.in_([1, 2])   # ADMIN=1, OPERATOR=2
                ).all()

            for user in users:
                # In-app notification
                notif = Notification(
                    user_id=user.id,
                    type=NotificationType.ALERT,
                    title=self._alert_title(alert),
                    message=alert.message,
                    link_url=f"/alerts",
                )
                self._db.add(notif)

                # Email (if user wants it)
                if self._user_wants_email(user):
                    self._send_alert_email(user, alert)

                # SMS (if user wants it and Twilio configured)
                if self._user_wants_sms(user):
                    self._send_alert_sms(user, alert)

            self._db.commit()

    def notify_system(self, user_id: int, title: str, message: str,
                      link_url: str = None):
        """Create a system/in-app notification for one user."""
        with self._app.app_context():
            from backend.models import Notification, NotificationType
            from backend.extensions import db

            notif = Notification(
                user_id=user_id,
                type=NotificationType.SYSTEM,
                title=title,
                message=message,
                link_url=link_url,
            )
            self._db.add(notif)
            self._db.commit()

    # ── Email ────────────────────────────────────────────────────────────────

    def _user_wants_email(self, user) -> bool:
        """Check if user has email notifications enabled."""
        # Default: True for admin/operator
        return bool(user.email)

    def _send_alert_email(self, user, alert):
        """Send alert as email via SMTP."""
        if not self._email_enabled or not self._mail:
            return

        from backend.models import AlertType, AlertState

        alert_type_name = AlertType(alert.alert_type).name if alert.alert_type else "ALERT"
        state_name = AlertState(alert.state).name if alert.state else "ACTIVE"

        subject = f"[HOLO-RTLS] {alert_type_name} — {alert.message or 'Alert triggered'}"

        html_body = f"""
        <html><body style="font-family: Arial, sans-serif; color: #1a1a2e;">
        <div style="background: #0a0a1a; color: #e0e0e0; padding: 20px; border-radius: 8px;">
          <h2 style="color: #ff4444; margin-top: 0;">⚠️ HOLO-RTLS Alert</h2>
          <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 6px 0; color: #888;">Type</td>
                <td><strong style="color: #ff7043;">{alert_type_name}</strong></td></tr>
            <tr><td style="padding: 6px 0; color: #888;">State</td>
                <td>{state_name}</td></tr>
            <tr><td style="padding: 6px 0; color: #888;">Message</td>
                <td style="color: #e0e0e0;">{alert.message or '—'}</td></tr>
            <tr><td style="padding: 6px 0; color: #888;">Triggered</td>
                <td>{alert.triggered_at.strftime('%Y-%m-%d %H:%M:%S UTC') if alert.triggered_at else '—'}</td></tr>
            <tr><td style="padding: 6px 0; color: #888;">Position</td>
                <td>x={alert.pos_x:.2f}, y={alert.pos_y:.2f}, z={alert.pos_z:.2f}</td></tr>
          </table>
          <p style="margin-top: 20px; font-size: 12px; color: #555;">
            Acknowledge at: <a href="#" style="color: #00e5ff;">HOLO-RTLS Dashboard</a>
          </p>
        </div>
        </body></html>
        """

        try:
            msg = Message(
                subject=subject,
                recipients=[user.email],
                html=html_body,
                sender=self._app.config.get("MAIL_DEFAULT_SENDER"),
            )
            self._mail.send(msg)
            logger.info(f"Alert email sent to {user.email}")
        except Exception as e:
            logger.error(f"Failed to send alert email to {user.email}: {e}")

    # ── SMS via Twilio ───────────────────────────────────────────────────────

    def _user_wants_sms(self, user) -> bool:
        """Check if user has SMS notifications enabled."""
        return bool(getattr(user, "phone", None))

    def _send_alert_sms(self, user, alert):
        """Send alert as SMS via Twilio."""
        if not self._sms_enabled:
            return

        from backend.models import AlertType
        alert_type_name = AlertType(alert.alert_type).name if alert.alert_type else "ALERT"

        body = (
            f"[HOLO-RTLS] {alert_type_name}: {alert.message or 'Alert'} "
            f"| Acknowledge at dashboard"
        )

        try:
            if self._twilio_client:
                self._twilio_client.messages.create(
                    to=user.phone,
                    from_=self._twilio_config["from_number"],
                    body=body,
                )
                logger.info(f"Alert SMS sent to {user.phone}")
        except Exception as e:
            logger.error(f"Failed to send SMS to {user.phone}: {e}")

    def configure_twilio(self, account_sid: str, auth_token: str, from_number: str):
        """Configure Twilio SMS. Call this from settings service."""
        try:
            from twilio.rest import Client
            self._twilio_client = Client(account_sid, auth_token)
            self._twilio_config = {"from_number": from_number}
            self._sms_enabled = True
            logger.info("Twilio SMS configured")
        except ImportError:
            logger.warning("twilio not installed — SMS disabled")
        except Exception as e:
            logger.error(f"Twilio config error: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _alert_title(self, alert) -> str:
        from backend.models import AlertType
        try:
            return f"⚠️ {AlertType(alert.alert_type).name} Alert"
        except Exception:
            return "⚠️ Alert"


# ── Singleton ─────────────────────────────────────────────────────────────────
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> Optional[NotificationService]:
    return _notification_service


def init_notification_service(db_session, app: Flask) -> NotificationService:
    global _notification_service
    _notification_service = NotificationService(db_session, app)
    return _notification_service
