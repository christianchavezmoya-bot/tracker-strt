"""Alerts API — Phase 4 stub."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.models import Alert, AlertState, AlertType, AuditLog, Tracker
from backend.utils.decorators import require_permission
from backend.services.rbac_service import Permission

alerts_bp = Blueprint("alerts", __name__, url_prefix="/api/alerts")


@alerts_bp.route("", methods=["GET"])
@jwt_required()
def list_alerts():
    q = Alert.query
    if request.args.get("state"):
        q = q.filter_by(state=int(request.args["state"]))
    if request.args.get("alert_type"):
        q = q.filter_by(alert_type=int(request.args["alert_type"]))
    if request.args.get("tracker_id"):
        q = q.filter_by(tracker_id=int(request.args["tracker_id"]))
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
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
    items = Alert.query.filter(
        Alert.state.in_([AlertState.ACTIVE, AlertState.ESCALATED])
    ).order_by(Alert.triggered_at.desc()).all()
    return jsonify({"items": [a.to_dict() for a in items], "total": len(items)})


@alerts_bp.route("/<int:alert_id>/acknowledge", methods=["POST"])
@jwt_required()
@require_permission(Permission.ACKNOWLEDGE_ALERT)
def acknowledge_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    body = request.get_json() or {}
    user_id = int(get_jwt_identity())
    from datetime import datetime, timezone
    alert.state = AlertState.ACKNOWLEDGED
    alert.acknowledged_by_id = user_id
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledgement_notes = body.get("notes")
    db.session.commit()
    AuditLog.log(action="alert.acknowledge", user_id=user_id,
                 entity_type="Alert", entity_id=alert.id)
    return jsonify({"alert": alert.to_dict()})


@alerts_bp.route("/<int:alert_id>/resolve", methods=["POST"])
@jwt_required()
@require_permission(Permission.ACKNOWLEDGE_ALERT)
def resolve_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    from datetime import datetime, timezone
    alert.state = AlertState.RESOLVED
    alert.resolved_at = datetime.now(timezone.utc)
    db.session.commit()
    AuditLog.log(action="alert.resolve", user_id=int(get_jwt_identity()),
                 entity_type="Alert", entity_id=alert.id)
    return jsonify({"alert": alert.to_dict()})
