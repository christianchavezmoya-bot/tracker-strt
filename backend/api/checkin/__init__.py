"""
HOLO-RTLS — Check-in / muster API (personnel accountability).
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from backend.extensions import db
from backend.models import Tracker, CheckInLog, AuditLog, WifiNode
from backend.models.tracker import CheckInStatus
from backend.services.rbac_service import Permission
from backend.utils.decorators import require_permission

checkin_bp = Blueprint("checkin", __name__, url_prefix="/api/checkin")


@checkin_bp.route("/status", methods=["GET"])
@jwt_required()
def muster_status():
    """Muster board: who is checked in / out / missing."""
    trackers = Tracker.query.all()
    items = []
    counts = {"CHECKED_IN": 0, "CHECKED_OUT": 0, "UNCHECKED": 0}
    for t in trackers:
        try:
            status = CheckInStatus(t.check_status).name
        except ValueError:
            status = "UNCHECKED"
        counts[status] = counts.get(status, 0) + 1
        items.append({
            "tracker_id": t.id,
            "hardware_id": t.hardware_id,
            "assigned_name": t.assigned_name,
            "check_status": status,
            "current_section": t.current_section_name,
            "last_report_time": t.last_report_time,
            "position": {"x": t.pos_x, "y": t.pos_y, "z": t.pos_z},
        })
    return jsonify({"items": items, "counts": counts, "total": len(items)})


@checkin_bp.route("/<int:tracker_id>", methods=["POST"])
@jwt_required()
@require_permission(Permission.MANAGE_TRACKER)
def set_checkin(tracker_id):
    """Set check-in / check-out. Body: { status: CHECKED_IN|CHECKED_OUT|UNCHECKED, node_id? }"""
    tracker = Tracker.query.get_or_404(tracker_id)
    body = request.get_json() or {}
    raw = body.get("status", "CHECKED_IN")
    try:
        if isinstance(raw, int):
            status = CheckInStatus(raw)
        else:
            status = CheckInStatus[str(raw).upper()]
    except (KeyError, ValueError):
        return jsonify({"error": "Invalid status"}), 400

    tracker.check_status = int(status)

    node_id = body.get("node_id")
    if node_id is None:
        node = WifiNode.query.first()
        node_id = node.id if node else None

    if node_id is not None and status in (CheckInStatus.CHECKED_IN, CheckInStatus.CHECKED_OUT):
        direction = "check_in" if status == CheckInStatus.CHECKED_IN else "check_out"
        db.session.add(CheckInLog(
            tracker_id=tracker.id,
            node_id=int(node_id),
            direction=direction,
            timestamp=datetime.now(timezone.utc),
        ))

    db.session.commit()
    AuditLog.log(
        action="checkin.set",
        user_id=int(get_jwt_identity()),
        entity_type="Tracker",
        entity_id=tracker.id,
        details=f'{{"status": "{status.name}"}}',
    )
    return jsonify({"tracker": tracker.to_dict(), "status": status.name})
