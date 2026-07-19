"""Web Push (VAPID) delivery for alert notifications."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from backend import config

logger = logging.getLogger(__name__)


def is_push_configured() -> bool:
    return bool(config.WEB_PUSH_ENABLED)


def send_alert_push(alert, user_ids: Iterable[int]) -> int:
    """
    Send Web Push to subscribed browsers for the given users.
    Returns count of successful sends (best-effort; stale subs removed).
    """
    if not is_push_configured():
        return 0

    ids = list({int(u) for u in user_ids})
    if not ids:
        return 0

    try:
        from backend.models.integrations import PushSubscription
        from backend.extensions import db
    except Exception as e:
        logger.warning("Push models unavailable: %s", e)
        return 0

    subs = PushSubscription.query.filter(PushSubscription.user_id.in_(ids)).all()
    if not subs:
        return 0

    title = _alert_title(alert)
    body = getattr(alert, "message", None) or title
    url = f"/?alert={getattr(alert, 'id', '')}"
    payload = json.dumps({"title": title, "body": body, "url": url})

    sent = 0
    stale: List[PushSubscription] = []
    for sub in subs:
        ok, remove = _send_one(sub.subscription_info(), payload)
        if ok:
            sent += 1
            sub.last_used_at = datetime.now(timezone.utc)
        elif remove:
            stale.append(sub)

    if stale:
        for sub in stale:
            db.session.delete(sub)
        db.session.commit()
    else:
        db.session.commit()

    return sent


def _alert_title(alert) -> str:
    try:
        from backend.models.alert import AlertType
        return f"HOLO-RTLS · {AlertType(alert.alert_type).name.replace('_', ' ')}"
    except Exception:
        return "HOLO-RTLS Alert"


def _send_one(subscription_info: dict, payload: str) -> tuple[bool, bool]:
    """Returns (success, should_remove_subscription)."""
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush not installed — Web Push disabled")
        return False, False

    vapid = {
        "private_key": config.VAPID_PRIVATE_KEY,
        "public_key": config.VAPID_PUBLIC_KEY,
        "claims": {"sub": config.VAPID_CLAIMS_EMAIL},
    }
    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=vapid["private_key"],
            vapid_claims=vapid["claims"],
        )
        return True, False
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (404, 410):
            return False, True
        logger.warning("Web push failed: %s", e)
        return False, False
    except Exception as e:
        logger.warning("Web push error: %s", e)
        return False, False
