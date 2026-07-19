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
    === A
    tags:
      - Alerts
    summary: List alerts with filtering
    description: Returns paginated alerts filtered by state, type, tracker, section, and time range.
    security:
      - Bearer: []
    parameters:
      - in: query
        name: state
        schema:
          type: string
          enum: [ACTIVE, ACKNOWLEDGED, RESOLVED, ESCALATED]
        description: Filter by alert state
      - in: query
        name: alert_type
        schema:
          type: string
        description: Filter by alert type (NO_SIGNAL, LOW_BATTERY, RESTRICTED_ZONE, etc.)
      - in: query
        name: tracker_id
        schema:
          type: integer
        description: Filter by tracker ID
      - in: query
        name: section
        schema:
          type: string
        description: Filter by section name (partial match)
      - in: query
        name: since
        schema:
          type: string
          format: date-time
        description: Filter alerts from this ISO datetime (default: last 24h)
      - in: query
        name: page
        schema:
          type: integer
          default: 1
        description: Page number
      - in: query
        name: per_page
        schema:
          type: integer
          default: 50
          maximum: 200
        description: Items per page
    responses:
      200:
        description: Paginated alerts list
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
            total: { type: integer }
            page: { type: integer }
            per_page: { type: integer }
            pages: { type: integer }
    ===
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
    """
    === A
    tags:
      - Alerts
    summary: Get active alerts
    description: Returns all unacknowledged alerts (ACTIVE and ESCALATED states).
    security:
      - Bearer: []
    responses:
      200:
        description: Active alerts list
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
            total: { type: integer }
            unacknowledged: { type: integer }
    ===
    """
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
    """
    === A
    tags:
      - Alerts
    summary: Get alert counts by type and state
    description: Returns aggregated counts of alerts grouped by alert type and state.
    security:
      - Bearer: []
    responses:
      200:
        description: Alert counts
        schema:
          type: object
          properties:
            by_type:
              type: object
              additionalProperties:
                type: integer
            by_state:
              type: object
              additionalProperties:
                type: integer
            total: { type: integer }
    ===
    """
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
    """
    === A
    tags:
      - Alerts
    summary: Get alert statistics for dashboard
    description: Returns summary statistics including total, active, today's count, and average resolution time.
    security:
      - Bearer: []
    responses:
      200:
        description: Dashboard statistics
        schema:
          type: object
          properties:
            total: { type: integer }
            active: { type: integer }
            today: { type: integer }
            avg_resolution_seconds: { type: number }
            alert_service_stats: { type: object }
    ===
    """
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
    """
    === A
    tags:
      - Alerts
    summary: Get a single alert
    description: Returns details for a specific alert by ID.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: alert_id
        required: true
        schema:
          type: integer
        description: Alert ID
    responses:
      200:
        description: Alert details
        schema:
          type: object
          properties:
            alert:
              type: object
      404:
        description: Alert not found
    ===
    """
    alert = Alert.query.get_or_404(alert_id)
    return jsonify({"alert": alert.to_dict()})


# ── Acknowledge ───────────────────────────────────────────────────────────────

@alerts_bp.route("/<int:alert_id>/acknowledge", methods=["POST"])
@jwt_required()
@require_permission(Permission.ACKNOWLEDGE_ALERT)
def acknowledge_alert(alert_id):
    """
    === A
    tags:
      - Alerts
    summary: Acknowledge an alert
    description: Marks an alert as acknowledged. Requires ACKNOWLEDGE_ALERT permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: alert_id
        required: true
        schema:
          type: integer
        description: Alert ID
      - in: body
        name: body
        schema:
          type: object
          properties:
            notes:
              type: string
              description: Optional acknowledgement notes
    responses:
      200:
        description: Alert acknowledged
        schema:
          type: object
          properties:
            alert: { type: object }
      404:
        description: Alert not found
    ===
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
    === A
    tags:
      - Alerts
    summary: Resolve an alert
    description: Marks an alert as resolved. Requires ACKNOWLEDGE_ALERT permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: alert_id
        required: true
        schema:
          type: integer
        description: Alert ID
      - in: body
        name: body
        schema:
          type: object
          properties:
            notes:
              type: string
              description: Optional resolution notes
    responses:
      200:
        description: Alert resolved
        schema:
          type: object
          properties:
            alert: { type: object }
      404:
        description: Alert not found
    ===
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
    """
    === A
    tags:
      - Alerts
    summary: Acknowledge all active alerts
    description: Marks all active alerts as acknowledged. Requires ACKNOWLEDGE_ALERT permission.
    security:
      - Bearer: []
    responses:
      200:
        description: Alerts acknowledged
        schema:
          type: object
          properties:
            acknowledged: { type: integer }
            message: { type: string }
    ===
    """
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
    """
    === A
    tags:
      - Alerts
    summary: List user notifications
    description: Returns the current user's in-app notifications with optional unread filter.
    security:
      - Bearer: []
    parameters:
      - in: query
        name: unread
        schema:
          type: boolean
          default: false
        description: Filter to unread notifications only
      - in: query
        name: page
        schema:
          type: integer
          default: 1
        description: Page number
      - in: query
        name: per_page
        schema:
          type: integer
          default: 20
          maximum: 50
        description: Items per page
    responses:
      200:
        description: Notifications list
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
            unread_count: { type: integer }
            total: { type: integer }
            page: { type: integer }
    ===
    """
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
    """
    === A
    tags:
      - Alerts
    summary: Mark notification as read
    description: Marks a specific notification as read for the current user.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: notif_id
        required: true
        schema:
          type: integer
        description: Notification ID
    responses:
      200:
        description: Notification updated
        schema:
          type: object
          properties:
            notification: { type: object }
      404:
        description: Notification not found
    ===
    """
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
    """
    === A
    tags:
      - Alerts
    summary: Mark all notifications as read
    description: Marks all unread notifications as read for the current user.
    security:
      - Bearer: []
    responses:
      200:
        description: All notifications marked as read
        schema:
          type: object
          properties:
            marked_read: { type: integer }
    ===
    """
    user_id = int(get_jwt_identity())
    count = db.session.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
    ).update({Notification.is_read: True})
    db.session.commit()
    return jsonify({"marked_read": count})


# ── Alarm trigger (downlink via MQTT) ─────────────────────────────────────────

@alerts_bp.route("/trigger", methods=["POST"])
@jwt_required()
@require_permission(Permission.TRIGGER_ALARM)
def trigger_alarm():
    """
    === A
    tags:
      - Alerts
    summary: Trigger an audible alarm on a tracker
    description: Sends a downlink MQTT message to make a specific tracker emit
    an audible alarm. Requires TRIGGER_ALARM permission.
    security:
      - Bearer: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [tracker_id]
            properties:
              tracker_id:
                type: integer
                description: ID of the tracker to alert
              message:
                type: string
                description: Optional alert message
    responses:
      200:
        description: Alarm triggered successfully
        schema:
          type: object
          properties:
            success: { type: boolean }
            tracker_id: { type: integer }
            message: { type: string }
      400:
        description: Missing tracker_id
      404:
        description: Tracker not found
      403:
        description: Permission denied
    ===
    """
    body = request.get_json() or {}
    tracker_id = body.get("tracker_id")
    if not tracker_id:
        return jsonify({"error": "tracker_id is required"}), 400

    from backend.models import Tracker
    tracker = Tracker.query.get(tracker_id)
    if not tracker:
        return jsonify({"error": "Tracker not found"}), 404

    # Publish to MQTT — downstream firmware/hardware bridge subscribes to this
    from backend.api.stream import get_mqtt_publisher
    import json
    mqtt = get_mqtt_publisher()
    alarm_payload = {
        "type": "alarm_trigger",
        "tracker_id": tracker_id,
        "hardware_id": tracker.hardware_id,
        "message": body.get("message", "Personnel alarm triggered"),
        "triggered_by": int(get_jwt_identity()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if mqtt and mqtt.is_connected:
        mqtt.publish("rtls/alarms/trigger", json.dumps(alarm_payload), qos=1)
        logger.info(f"Alarm triggered for tracker {tracker_id} ({tracker.hardware_id})")
    else:
        logger.warning(f"MQTT not connected — alarm for tracker {tracker_id} not published")

    # Log to audit trail
    from backend.models import AuditLog
    AuditLog.log(
        action="alarm.trigger",
        user_id=int(get_jwt_identity()),
        entity_type="Tracker",
        entity_id=tracker_id,
        details=f"Alarm triggered for tracker {tracker.hardware_id}: {body.get('message', '')}",
    )

    return jsonify({
        "success": True,
        "tracker_id": tracker_id,
        "message": "Alarm triggered",
    })
