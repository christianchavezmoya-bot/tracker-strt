"""Webhooks + report schedules API."""
from __future__ import annotations
import json
import hashlib
import hmac
import logging
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from backend.extensions import db
from backend.models import WebhookEndpoint, ReportSchedule, AuditLog
from backend.services.rbac_service import Permission
from backend.utils.decorators import require_permission

logger = logging.getLogger(__name__)

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/api/webhooks")
schedules_bp = Blueprint("schedules", __name__, url_prefix="/api/reports/schedules")


# ── Webhook CRUD ──────────────────────────────────────────────────────────────

@webhooks_bp.route("", methods=["GET"])
@jwt_required()
@require_permission(Permission.MANAGE_API_KEY)
def list_webhooks():
    rows = WebhookEndpoint.query.order_by(WebhookEndpoint.id.desc()).all()
    return jsonify({"items": [r.to_dict() for r in rows], "total": len(rows)})


@webhooks_bp.route("", methods=["POST"])
@jwt_required()
@require_permission(Permission.MANAGE_API_KEY)
def create_webhook():
    body = request.get_json() or {}
    name = (body.get("name") or "").strip()
    url = (body.get("url") or "").strip()
    if not name or not url:
        return jsonify({"error": "name and url are required"}), 400
    events = body.get("events") or ["alert.created"]
    if isinstance(events, str):
        events = [e.strip() for e in events.split(",") if e.strip()]
    row = WebhookEndpoint(
        name=name,
        url=url,
        events=json.dumps(events),
        secret=(body.get("secret") or "")[:120] or None,
        is_active=bool(body.get("is_active", True)),
    )
    db.session.add(row)
    db.session.commit()
    AuditLog.log(
        action="webhook.create",
        user_id=int(get_jwt_identity()),
        entity_type="WebhookEndpoint",
        entity_id=row.id,
    )
    return jsonify({"webhook": row.to_dict()}), 201


@webhooks_bp.route("/<int:wid>", methods=["PATCH"])
@jwt_required()
@require_permission(Permission.MANAGE_API_KEY)
def update_webhook(wid):
    row = WebhookEndpoint.query.get_or_404(wid)
    body = request.get_json() or {}
    if "name" in body:
        row.name = str(body["name"]).strip()
    if "url" in body:
        row.url = str(body["url"]).strip()
    if "events" in body:
        ev = body["events"]
        if isinstance(ev, str):
            ev = [e.strip() for e in ev.split(",") if e.strip()]
        row.events = json.dumps(ev)
    if "secret" in body:
        row.secret = (body["secret"] or "")[:120] or None
    if "is_active" in body:
        row.is_active = bool(body["is_active"])
    db.session.commit()
    return jsonify({"webhook": row.to_dict()})


@webhooks_bp.route("/<int:wid>", methods=["DELETE"])
@jwt_required()
@require_permission(Permission.MANAGE_API_KEY)
def delete_webhook(wid):
    row = WebhookEndpoint.query.get_or_404(wid)
    db.session.delete(row)
    db.session.commit()
    return jsonify({"message": "Deleted"})


@webhooks_bp.route("/<int:wid>/test", methods=["POST"])
@jwt_required()
@require_permission(Permission.MANAGE_API_KEY)
def test_webhook(wid):
    row = WebhookEndpoint.query.get_or_404(wid)
    ok, status = deliver_webhook(row, "webhook.test", {"message": "HOLO-RTLS test ping"})
    return jsonify({"ok": ok, "status": status, "webhook": row.to_dict()})


def deliver_webhook(endpoint: WebhookEndpoint, event: str, payload: dict) -> tuple:
    """POST event payload to a webhook endpoint. Returns (ok, status_str)."""
    body = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    raw = json.dumps(body, default=str)
    headers = {"Content-Type": "application/json", "X-HOLO-Event": event}
    if endpoint.secret:
        sig = hmac.new(endpoint.secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
        headers["X-HOLO-Signature"] = f"sha256={sig}"
    try:
        resp = requests.post(endpoint.url, data=raw, headers=headers, timeout=8)
        endpoint.last_delivery_at = datetime.now(timezone.utc)
        endpoint.last_status = f"{resp.status_code}"
        db.session.commit()
        return 200 <= resp.status_code < 300, endpoint.last_status
    except Exception as e:
        endpoint.last_delivery_at = datetime.now(timezone.utc)
        endpoint.last_status = f"error:{e}"
        db.session.commit()
        logger.warning("Webhook delivery failed %s: %s", endpoint.id, e)
        return False, endpoint.last_status


def dispatch_webhooks(event: str, payload: dict):
    """Fire all active webhooks subscribed to event (best-effort)."""
    rows = WebhookEndpoint.query.filter_by(is_active=True).all()
    for row in rows:
        events = []
        try:
            events = json.loads(row.events or "[]")
        except Exception:
            events = []
        if event in events or "*" in events:
            try:
                deliver_webhook(row, event, payload)
            except Exception as e:
                logger.warning("dispatch_webhooks: %s", e)


# ── Report schedules CRUD ─────────────────────────────────────────────────────

@schedules_bp.route("", methods=["GET"])
@jwt_required()
@require_permission(Permission.GENERATE_REPORT)
def list_schedules():
    rows = ReportSchedule.query.order_by(ReportSchedule.id.desc()).all()
    return jsonify({"items": [r.to_dict() for r in rows], "total": len(rows)})


@schedules_bp.route("", methods=["POST"])
@jwt_required()
@require_permission(Permission.GENERATE_REPORT)
def create_schedule():
    body = request.get_json() or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    row = ReportSchedule(
        name=name,
        report_type=(body.get("report_type") or "summary")[:40],
        cron=(body.get("cron") or "0 6 * * *")[:40],
        recipients=(body.get("recipients") or "")[:500],
        format=(body.get("format") or "csv")[:10],
        is_active=bool(body.get("is_active", True)),
    )
    db.session.add(row)
    db.session.commit()
    return jsonify({"schedule": row.to_dict()}), 201


@schedules_bp.route("/<int:sid>", methods=["PATCH"])
@jwt_required()
@require_permission(Permission.GENERATE_REPORT)
def update_schedule(sid):
    row = ReportSchedule.query.get_or_404(sid)
    body = request.get_json() or {}
    for field in ("name", "report_type", "cron", "recipients", "format"):
        if field in body and body[field] is not None:
            setattr(row, field, str(body[field])[:500 if field == "recipients" else 40])
    if "is_active" in body:
        row.is_active = bool(body["is_active"])
    db.session.commit()
    return jsonify({"schedule": row.to_dict()})


@schedules_bp.route("/<int:sid>/run", methods=["POST"])
@jwt_required()
@require_permission(Permission.GENERATE_REPORT)
def run_schedule_now(sid):
    """Deliver a schedule immediately (manual run)."""
    from backend.services.report_delivery import deliver_schedule_now
    row = ReportSchedule.query.get_or_404(sid)
    try:
        deliver_schedule_now(row)
        return jsonify({"message": "Report delivered", "schedule": row.to_dict()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@schedules_bp.route("/<int:sid>", methods=["DELETE"])
@jwt_required()
@require_permission(Permission.GENERATE_REPORT)
def delete_schedule(sid):
    row = ReportSchedule.query.get_or_404(sid)
    db.session.delete(row)
    db.session.commit()
    return jsonify({"message": "Deleted"})
