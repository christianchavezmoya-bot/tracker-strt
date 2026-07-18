"""
HOLO-RTLS — Alerts API
Full CRUD + acknowledge + resolve + history + stats + SSE subscription.
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.models import Alert, AlertState, AlertType, Notification, NotificationType
from backend.utils.decorators import require_permission
from backend.services.rbac_service import Permission

alerts_bp = Blueprint("alerts", __name__, url_prefix="/api/alerts")


# ── List & Filter ─────────────────────────────────────────────────────────────

@alerts_bp.route("", methods=["GET"])
@jwt_required()
def list_alerts():
    """
    GET /api/alerts
    Query params:
      state         — ACTIVE, ACKNOWLEDGED, RESOLVED, ESCALATED
      alert_type   — NO_SIGNAL, LOW_BATTERY, RESTRICTED_ZONE, etc.
      tracker_id    — filter by tracker
      section       — filter by section name (partial match)
      since         — ISO datetime (default: last 24h)
      page / per_page
    """
    q = Alert.query

    if request.args.get("state"):
        try:
            state_val = getattr(AlertState, request.args["state"], None)
            if state_val:
                q = q.filter(Alert.state == state_val.value)
        except Exception:
            pass

    if request.args.get("alert_type"):
        try:
            at_val = getattr(AlertType, request.args["alert_type"], None)
            if at_val:
                q = q.filter(Alert.alert_type == at_val.value)
        except Exception:
            pass

    if request.args.get("tracker_id"):
        q = q.filter(Alert.tracker_id == int(request.args["tracker_id"]))

    if request.args.get("section"):
        q = q.filter(Alert.section_name.ilike(f"%{request.args['section']}%"))

    if request.args.get("since"):
        try:
            since = datetime.fromisoformat(request.args["since"].replace("Z", "+00:00"))
            q = q.filter(Alert.triggered_at >= since)
        except Exception:
            pass
    else:
        # Default: last 24h
        cutoff = datetime.now(timezone.utc).replace(microsecond=0) - __import__("datetime").timedelta(hours=24)
        q = q.filter(Alert.triggered_at >= cutoff)

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    pagination = q.order_by(Alert.triggered_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [a.to_dict() for a in pagination.items],
        "total": pagination.total,
        "page": page, "per_page": per_page, "pages": pagination.pages,
    })


@alerts_bp.route("/active", methods=["GET"])
@jwt_required()
def active_alerts():
    """GET /api/alerts/active — All unacknowledged alerts."""
    items = Alert.query.filter(
        Alert.state.in_([AlertState.ACTIVE.value, AlertState.ESCALATED.value])
    ).order_by(Alert.triggered_at.desc()).all()
    return jsonify({
        "items": [a.to_dict() for a in items],
        "total": len(items),
        "unacknowledged": len(items),
    })


@alerts_bp.route("/counts", methods=["GET"])
@jwt_required()
def alert_counts():
    """GET /api/alerts/counts — Alert counts by type and state."""
    from sqlalchemy import func
    counts = db.session.query(
        Alert.alert_type,
        Alert.state,
        func.count(Alert.id)
    ).group_by(Alert.alert_type, Alert.state).all()

    by_type = {}
    by_state = {}
    for at, st, cnt in counts:
        at_name = AlertType(at).name if at else "UNKNOWN"
        st_name = AlertState(st).name if st else "UNKNOWN"
        by_type[at_name] = by_type.get(at_name, 0) + cnt
        by_state[st_name] = by_state.get(st_name, 0) + cnt

    return jsonify({
        "by_type": by_type,
        "by_state": by_state,
        "total": sum(counts, key=lambda x: x[2]) if counts else 0,
    })


@alerts_bp.route("/stats", methods=["GET"])
@jwt_required()
def alert_stats():
    """GET /api/alerts/stats — Summary stats for dashboard."""
    from sqlalchemy import func
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total = db.session.query(func.count(Alert.id)).scalar()
    active = db.session.query(func.count(Alert.id)).filter(
        Alert.state == AlertState.ACTIVE.value
    ).scalar()
    today_count = db.session.query(func.count(Alert.id)).filter(
        Alert.triggered_at >= today
    ).scalar()

    # Resolution time (avg for resolved alerts last 7 days)
    week_ago = now - timedelta(days=7)
    resolved = db.session.query(Alert).filter(
        Alert.state == AlertState.RESOLVED.value,
        Alert.resolved_at != None,
        Alert.triggered_at >= week_ago,
    ).all()
    if resolved:
        times = [(r.resolved_at - r.triggered_at).total_seconds() for r in resolved if r.resolved_at]
        avg_resolution = sum(times) / len(times) if times else 0
    else:
        avg_resolution = 0

    return jsonify({
        "total": total or 0,
        "active": active or 0,
        "today": today_count or 0,
        "avg_resolution_seconds": round(avg_resolution, 1),
        "alert_service_stats": _get_alert_service_stats(),
    })


def _get_alert_service_stats():
    from backend.services.alert_service import get_alert_service
    svc = get_alert_service()
    return svc.get_stats() if svc else {}


# ── Single alert ─────────────────────────────────────────────────────────────

@alerts_bp.route("/<int:alert_id>", methods=["GET"])
@jwt_required()
def get_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    return jsonify({"alert": alert.to_dict()})


# ── Acknowledge ───────────────────────────────────────────────────────────────

@alerts_bp.route("/<int:alert_id>/acknowledge", methods=["POST"])
@jwt_required()
@require_permission(Permission.ACKNOWLEDGE_ALERT)
def acknowledge_alert(alert_id):
    """
    POST /api/alerts/<id>/acknowledge
    Body: { "notes": "optional notes" }
    """
    alert = Alert.query.get_or_404(alert_id)
    body = request.get_json() or {}
    user_id = int(get_jwt_identity())

    alert.state = AlertState.ACKNOWLEDGED
    alert.acknowledged_by_id = user_id
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledgement_notes = body.get("notes", "").strip() or None
    db.session.commit()

    from backend.models import AuditLog
    AuditLog.log(action="alert.acknowledge", user_id=user_id,
                 entity_type="Alert", entity_id=alert.id,
                 details=f'Notes: {body.get("notes", "")}')

    # Broadcast resolution to SSE
    from backend.services.ingestion_loop import get_ingestion_loop
    loop = get_ingestion_loop()
    if loop:
        loop._broadcast_sse({
            "type": "alert_acknowledged",
            "alert": alert.to_dict(),
        })

    return jsonify({"alert": alert.to_dict()})


# ── Resolve ───────────────────────────────────────────────────────────────────

@alerts_bp.route("/<int:alert_id>/resolve", methods=["POST"])
@jwt_required()
@require_permission(Permission.ACKNOWLEDGE_ALERT)
def resolve_alert(alert_id):
    """
    POST /api/alerts/<id>/resolve
    Body: { "notes": "optional resolution notes" }
    """
    alert = Alert.query.get_or_404(alert_id)
    body = request.get_json() or {}
    user_id = int(get_jwt_identity())

    alert.state = AlertState.RESOLVED
    alert.resolved_at = datetime.now(timezone.utc)
    if body.get("notes"):
        alert.acknowledgement_notes = (alert.acknowledgement_notes or "") + f"; resolve: {body['notes']}"
    db.session.commit()

    from backend.models import AuditLog
    AuditLog.log(action="alert.resolve", user_id=user_id,
                 entity_type="Alert", entity_id=alert.id)

    from backend.services.ingestion_loop import get_ingestion_loop
    loop = get_ingestion_loop()
    if loop:
        loop._broadcast_sse({
            "type": "alert_resolved",
            "alert": alert.to_dict(),
        })

    return jsonify({"alert": alert.to_dict()})


# ── Bulk acknowledge ─────────────────────────────────────────────────────────

@alerts_bp.route("/acknowledge-all", methods=["POST"])
@jwt_required()
@require_permission(Permission.ACKNOWLEDGE_ALERT)
def acknowledge_all():
    """POST /api/alerts/acknowledge-all — Acknowledge all active alerts."""
    user_id = int(get_jwt_identity())
    count = Alert.query.filter(
        Alert.state == AlertState.ACTIVE.value
    ).update({
        Alert.state: AlertState.ACKNOWLEDGED.value,
        Alert.acknowledged_by_id: user_id,
        Alert.acknowledged_at: datetime.now(timezone.utc),
    })
    db.session.commit()
    return jsonify({"acknowledged": count, "message": f"{count} alerts acknowledged"})


# ── Notifications ──────────────────────────────────────────────────────────────

@alerts_bp.route("/notifications", methods=["GET"])
@jwt_required()
def list_notifications():
    """GET /api/alerts/notifications — Current user's in-app notifications."""
    user_id = int(get_jwt_identity())
    unread_only = request.args.get("unread", "false").lower() == "true"
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 50)

    q = db.session.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        q = q.filter(Notification.is_read == False)
    pagination = q.order_by(Notification.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)

    unread_count = db.session.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
    ).count()

    return jsonify({
        "items": [n.to_dict() for n in pagination.items],
        "unread_count": unread_count,
        "total": pagination.total,
        "page": page,
    })


@alerts_bp.route("/notifications/<int:notif_id>/read", methods=["POST"])
@jwt_required()
def mark_notification_read(notif_id):
    """POST /api/alerts/notifications/<id>/read — Mark as read."""
    user_id = int(get_jwt_identity())
    notif = db.session.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == user_id,
    ).first_or_404()
    notif.is_read = True
    db.session.commit()
    return jsonify({"notification": notif.to_dict()})


@alerts_bp.route("/notifications/read-all", methods=["POST"])
@jwt_required()
def mark_all_read():
    """POST /api/alerts/notifications/read-all — Mark all as read."""
    user_id = int(get_jwt_identity())
    count = db.session.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
    ).update({Notification.is_read: True})
    db.session.commit()
    return jsonify({"marked_read": count})
