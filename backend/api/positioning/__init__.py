"""
HOLO-RTLS — Positioning / History API
Read position history and snapshots for trackers.
"""
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from backend.extensions import db
from backend.models.positioning import TrackingHistory, PositionSnapshot
from backend.services.history_service import get_history_service

positioning_bp = Blueprint("positioning", __name__, url_prefix="/api/positioning")


# ── Live position snapshots ────────────────────────────────────────────────────
@positioning_bp.route("/live", methods=["GET"])
@jwt_required()
def live_positions():
    """
    GET /api/positioning/live
    Returns the latest position for every tracker (position_snapshot table).
    """
    snapshots = db.session.query(PositionSnapshot).all()
    return jsonify({
        "positions": [s.to_dict() for s in snapshots],
        "total": len(snapshots),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@positioning_bp.route("/live/<int:tracker_id>", methods=["GET"])
@jwt_required()
def live_tracker(tracker_id):
    """GET /api/positioning/live/<tracker_id> — Latest position for one tracker."""
    snap = db.session.query(PositionSnapshot).get(tracker_id)
    if not snap:
        return jsonify({"error": "Tracker not found"}), 404
    return jsonify({"position": snap.to_dict()})


# ── Position history ──────────────────────────────────────────────────────────
@positioning_bp.route("/history/<int:tracker_id>", methods=["GET"])
@jwt_required()
def tracker_history(tracker_id):
    """
    GET /api/positioning/history/<tracker_id>
    Query params:
      since     — ISO datetime string (default: last 1 hour)
      limit     — max records (default: 1000, max: 10000)
    """
    limit = min(int(request.args.get("limit", 1000)), 10000)
    since_str = request.args.get("since")
    since = None
    if since_str:
        try:
            since = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
        except ValueError:
            return jsonify({"error": "Invalid since format. Use ISO 8601."}), 400

    rows = db.session.query(TrackingHistory).filter(
        TrackingHistory.tracker_id == tracker_id
    ).order_by(TrackingHistory.timestamp.desc())

    if since:
        rows = rows.filter(TrackingHistory.timestamp >= since)

    rows = rows.limit(limit).all()
    return jsonify({
        "tracker_id": tracker_id,
        "history": [r.to_dict() for r in rows],
        "count": len(rows),
    })


@positioning_bp.route("/history/<int:tracker_id>/export", methods=["GET"])
@jwt_required()
def export_history(tracker_id):
    """
    GET /api/positioning/history/<tracker_id>/export?format=csv&since=...
    Returns CSV of position history for the tracker.
    """
    import csv
    from io import StringIO
    from flask import Response

    limit = min(int(request.args.get("limit", 10000)), 50000)
    since_str = request.args.get("since")
    since = None
    if since_str:
        try:
            since = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    rows = db.session.query(TrackingHistory).filter(
        TrackingHistory.tracker_id == tracker_id
    ).order_by(TrackingHistory.timestamp.asc())

    if since:
        rows = rows.filter(TrackingHistory.timestamp >= since)

    rows = rows.limit(limit).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "tracker_id", "x", "y", "z", "accuracy", "speed", "vx", "vy", "timestamp"])
    for r in rows:
        writer.writerow([r.id, r.tracker_id, r.x, r.y, r.z, r.accuracy, r.speed, r.vx, r.vy, r.timestamp.isoformat()])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tracker_{tracker_id}_history.csv"},
    )


# ── History stats ─────────────────────────────────────────────────────────────
@positioning_bp.route("/stats", methods=["GET"])
@jwt_required()
def history_stats():
    """GET /api/positioning/stats — History service stats + total records."""
    svc = get_history_service()
    if svc:
        return jsonify(svc.get_stats())
    return jsonify({"error": "History service not running"}), 503


# ── Calibration ──────────────────────────────────────────────────────────────
@positioning_bp.route("/calibration", methods=["GET"])
@jwt_required()
def get_calibration():
    """GET /api/positioning/calibration — Floor plan calibration status."""
    from backend.services.floor_plan_mapper import get_floor_plan_mapper
    svc = get_floor_plan_mapper()
    return jsonify({"status": svc.get_calibration_status()})


@positioning_bp.route("/calibration", methods=["POST"])
@jwt_required()
def add_calibration_point():
    """POST /api/positioning/calibration — Add a calibration point."""
    body = request.get_json() or {}
    required = ["pixel_x", "pixel_y", "real_x", "real_y"]
    for f in required:
        if f not in body:
            return jsonify({"error": f"Missing field: {f}"}), 400

    from backend.services.floor_plan_mapper import get_floor_plan_mapper
    svc = get_floor_plan_mapper()
    section_id = int(body.get("section_id", 0))
    svc.add_calibration_point(
        section_id=section_id,
        pixel_x=float(body["pixel_x"]),
        pixel_y=float(body["pixel_y"]),
        real_x=float(body["real_x"]),
        real_y=float(body["real_y"]),
    )
    mapper = svc.get_mapper(section_id)
    return jsonify({
        "calibration_points": svc.get_calibration_points(section_id),
        "is_calibrated": mapper.is_calibrated,
        "calibration_error": svc.calibration_error(section_id),
    })
