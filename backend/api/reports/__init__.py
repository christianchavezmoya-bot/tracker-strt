"""Reports API — Phase 6 stub (CSV generation + email delivery)."""
from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timezone, timedelta
import csv, io
from backend.extensions import db
from backend.models import Tracker, Alert, TrackingHistory
from backend.utils.decorators import require_permission
from backend.services.rbac_service import Permission

reports_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


def make_csv_response(rows, filename):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else [])
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@reports_bp.route("/daily", methods=["GET"])
@jwt_required()
@require_permission(Permission.GENERATE_REPORT)
def daily_summary():
    date_str = request.args.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return jsonify({"error": "Invalid date format (YYYY-MM-DD)"}), 400

    active_count = Tracker.query.filter_by(asset_state=1, alert_status=0).count()
    alert_count = Alert.query.filter(
        Alert.triggered_at >= day,
        Alert.triggered_at < day + timedelta(days=1),
    ).count()
    tracker_count = Tracker.query.count()

    rows = [{
        "date": date_str,
        "total_trackers": tracker_count,
        "active_trackers": active_count,
        "total_alerts": alert_count,
    }]
    return make_csv_response(rows, f"daily_summary_{date_str}.csv")


@reports_bp.route("/battery", methods=["GET"])
@jwt_required()
@require_permission(Permission.GENERATE_REPORT)
def battery_report():
    trackers = Tracker.query.filter(Tracker.battery_level < 100).order_by(Tracker.battery_level).all()
    rows = [{
        "hardware_id": t.hardware_id,
        "assigned_name": t.assigned_name,
        "battery_level": t.battery_level,
        "category": t.category_name,
    } for t in trackers]
    return make_csv_response(rows, "battery_report.csv")


@reports_bp.route("/distance", methods=["GET"])
@jwt_required()
@require_permission(Permission.GENERATE_REPORT)
def distance_report():
    """Distance traveled per tracker (from last 24h of history)."""
    tracker_id = request.args.get("tracker_id", type=int)
    since = datetime.now(timezone.utc) - timedelta(days=1)
    q = TrackingHistory.query.filter(TrackingHistory.timestamp >= since.timestamp())
    if tracker_id:
        q = q.filter_by(tracker_id=tracker_id)
    rows = [
        {
            "tracker_id": h.tracker_id,
            "pos_x": h.pos_x,
            "pos_y": h.pos_y,
            "pos_z": h.pos_z,
            "section_name": h.section_name,
            "timestamp": h.timestamp,
        }
        for h in q.order_by(TrackingHistory.tracker_id, TrackingHistory.timestamp).all()
    ]
    return make_csv_response(rows, f"distance_history.csv")
