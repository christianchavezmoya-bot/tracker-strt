"""Reports API — Phase 8 (enhanced CSV + JSON analytics)."""
from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timezone, timedelta
import csv, io
from backend.extensions import db
from backend.models import Tracker, Alert, TrackingHistory
from backend.models.alert import AlertType
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


def _date_range(days=7):
    """Parse date range from query params."""
    end_str = request.args.get("end", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    start_str = request.args.get("start", (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d"))
    try:
        end = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        start = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return start, end
    except ValueError:
        return None, None


# ── Analytics (JSON, for charts) ───────────────────────────────────────────────

@reports_bp.route("/summary", methods=["GET"])
@jwt_required()
def summary():
    """
    === A
    tags:
      - Reports
    summary: Get analytics summary
    description: Returns daily alert counts, tracker totals, and average response time for a date range.
    security:
      - Bearer: []
    parameters:
      - in: query
        name: days
        schema:
          type: integer
          default: 30
        description: Number of past days to include
      - in: query
        name: start
        schema:
          type: string
          format: date
          description: Start date (YYYY-MM-DD)
      - in: query
        name: end
        schema:
          type: string
          format: date
          description: End date (YYYY-MM-DD)
    responses:
      200:
        description: Summary data for charting
        schema:
          type: object
          properties:
            period:
              type: object
              properties:
                start: { type: string }
                end: { type: string }
                days: { type: integer }
            totals:
              type: object
              properties:
                total_trackers: { type: integer }
                active_trackers: { type: integer }
                total_alerts: { type: integer }
                acknowledged_alerts: { type: integer }
                unresolved_alerts: { type: integer }
                avg_response_minutes: { type: number }
            alert_series:
              type: array
              items:
                type: object
                properties:
                  date: { type: string }
                  count: { type: integer }
      400:
        description: Invalid date format
    ===
    """
    days = int(request.args.get("days", 30))
    start, end = _date_range(days)
    if start is None:
        return jsonify({"error": "Invalid date format (YYYY-MM-DD)"}), 400

    rows = db.session.execute(db.text("""
        SELECT DATE(alerted_at) as day,
               COUNT(*) as alert_count
        FROM (SELECT DATE(triggered_at) as alerted_at FROM alerts
              WHERE triggered_at >= :start AND triggered_at < :end
              UNION ALL
              SELECT DATE(triggered_at) as alerted_at FROM alerts
              WHERE acknowledged_at >= :start AND acknowledged_at < :end)
        GROUP BY day ORDER BY day
    """), {"start": start, "end": end}).fetchall()

    # Fill in missing days
    series = {}
    current = start
    while current < end:
        series[current.strftime("%Y-%m-%d")] = 0
        current += timedelta(days=1)
    for row in rows:
        series[str(row[0])] = row[1]

    total_trackers = Tracker.query.count()
    active_trackers = Tracker.query.filter_by(asset_state=1).count()
    total_alerts = Alert.query.filter(
        Alert.triggered_at >= start,
        Alert.triggered_at < end,
    ).count()
    acknowledged_alerts = Alert.query.filter(
        Alert.triggered_at >= start,
        Alert.triggered_at < end,
        Alert.state.in_([2, 3]),   # ACKNOWLEDGED or RESOLVED
    ).count()
    unresolved_alerts = Alert.query.filter(
        Alert.triggered_at >= start,
        Alert.triggered_at < end,
        Alert.state == 1,           # ACTIVE
    ).count()
    avg_response_minutes = None
    # Avg acknowledgement time
    ack_rows = db.session.execute(db.text("""
        SELECT AVG((julianday(acknowledged_at) - julianday(triggered_at)) * 1440)
               FROM alerts
        WHERE acknowledged_at IS NOT NULL
          AND acknowledged_at >= :start AND acknowledged_at < :end
          AND triggered_at >= :start
    """), {"start": start, "end": end}).fetchone()
    if ack_rows and ack_rows[0]:
        avg_response_minutes = round(float(ack_rows[0]), 1)

    return jsonify({
        "period": {"start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d"), "days": days},
        "totals": {
            "total_trackers": total_trackers,
            "active_trackers": active_trackers,
            "total_alerts": total_alerts,
            "acknowledged_alerts": acknowledged_alerts,
            "unresolved_alerts": unresolved_alerts,
            "avg_response_minutes": avg_response_minutes,
        },
        "alert_series": [
            {"date": d, "count": c} for d, c in sorted(series.items())
        ],
    })


@reports_bp.route("/tracker-activity", methods=["GET"])
@jwt_required()
def tracker_activity():
    """
    === A
    tags:
      - Reports
    summary: Get tracker activity report
    description: Returns per-tracker activity summary including distance traveled and alert counts.
    security:
      - Bearer: []
    parameters:
      - in: query
        name: days
        schema:
          type: integer
          default: 7
        description: Number of past days to include
    responses:
      200:
        description: Per-tracker activity data
        schema:
          type: object
          properties:
            trackers:
              type: array
              items:
                type: object
                properties:
                  tracker_id: { type: integer }
                  hardware_id: { type: string }
                  assigned_name: { type: string }
                  category: { type: string }
                  position_count: { type: integer }
                  distance_m: { type: number }
                  alert_count: { type: integer }
                  first_seen: { type: string, format: date-time }
                  last_seen: { type: string, format: date-time }
            days: { type: integer }
    ===
    """
    days = int(request.args.get("days", 7))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    trackers = Tracker.query.filter(Tracker.asset_state == 1).all()
    result = []
    for t in trackers:
        history_rows = TrackingHistory.query.filter(
            TrackingHistory.tracker_id == t.id,
            TrackingHistory.timestamp >= since,
        ).order_by(TrackingHistory.timestamp).all()

        if not history_rows:
            result.append({
                "tracker_id": t.id,
                "hardware_id": t.hardware_id,
                "assigned_name": t.assigned_name,
                "category": t.category_name,
                "position_count": 0,
                "distance_m": 0.0,
                "first_seen": None,
                "last_seen": None,
            })
            continue

        # Compute distance traveled
        dist = 0.0
        for i in range(1, len(history_rows)):
            p1, p2 = history_rows[i - 1], history_rows[i]
            dx = p2.x - p1.x
            dy = p2.y - p1.y
            dist += (dx * dx + dy * dy) ** 0.5

        alert_count = Alert.query.filter(
            Alert.tracker_id == t.id,
            Alert.triggered_at >= since,
        ).count()

        result.append({
            "tracker_id": t.id,
            "hardware_id": t.hardware_id,
            "assigned_name": t.assigned_name,
            "category": t.category_name,
            "position_count": len(history_rows),
            "distance_m": round(dist, 2),
            "alert_count": alert_count,
            "first_seen": history_rows[0].timestamp.isoformat() if history_rows else None,
            "last_seen": history_rows[-1].timestamp.isoformat() if history_rows else None,
        })

    result.sort(key=lambda x: x["distance_m"], reverse=True)
    return jsonify({"trackers": result, "days": days})


@reports_bp.route("/alert-breakdown", methods=["GET"])
@jwt_required()
def alert_breakdown():
    """
    === A
    tags:
      - Reports
    summary: Get alert breakdown by type
    description: Returns alert counts grouped by alert type for a time period.
    security:
      - Bearer: []
    parameters:
      - in: query
        name: days
        schema:
          type: integer
          default: 30
        description: Number of past days to include
    responses:
      200:
        description: Alert breakdown by type
        schema:
          type: object
          properties:
            breakdown:
              type: array
              items:
                type: object
                properties:
                  type: { type: string }
                  count: { type: integer }
            days: { type: integer }
            since: { type: string, format: date-time }
    ===
    """
    days = int(request.args.get("days", 30))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.session.execute(db.text("""
        SELECT alert_type, COUNT(*) as count
        FROM alerts
        WHERE triggered_at >= :since
        GROUP BY alert_type
        ORDER BY count DESC
    """), {"since": since}).fetchall()

    breakdown = []
    for row in rows:
        try:
            name = AlertType(row[0]).name
        except ValueError:
            name = f"TYPE_{row[0]}"
        breakdown.append({"type": name, "count": row[1]})

    return jsonify({"breakdown": breakdown, "days": days, "since": since.isoformat()})


# ── CSV Exports ────────────────────────────────────────────────────────────────

@reports_bp.route("/daily", methods=["GET"])
@jwt_required()
@require_permission(Permission.GENERATE_REPORT)
def daily_summary():
    """
    === A
    tags:
      - Reports
    summary: Export daily summary as CSV
    description: Returns a CSV file with daily tracker and alert summary. Requires GENERATE_REPORT permission.
    security:
      - Bearer: []
    parameters:
      - in: query
        name: date
        schema:
          type: string
          format: date
        description: Date to summarize (YYYY-MM-DD, default today)
    responses:
      200:
        description: CSV file download
        content:
          text/csv:
            schema:
              type: string
              format: binary
      400:
        description: Invalid date format
    ===
    """
    date_str = request.args.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return jsonify({"error": "Invalid date format (YYYY-MM-DD)"}), 400

    active_count = Tracker.query.filter_by(asset_state=1).count()
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
    """
    === A
    tags:
      - Reports
    summary: Export battery report as CSV
    description: Returns a CSV file listing all trackers with battery level below 100%. Requires GENERATE_REPORT permission.
    security:
      - Bearer: []
    responses:
      200:
        description: CSV file download
        content:
          text/csv:
            schema:
              type: string
              format: binary
    ===
    """
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
    """
    === A
    tags:
      - Reports
    summary: Export distance history as CSV
    description: Returns a CSV file with position history for distance analysis. Requires GENERATE_REPORT permission.
    security:
      - Bearer: []
    parameters:
      - in: query
        name: tracker_id
        schema:
          type: integer
        description: Filter by specific tracker ID
    responses:
      200:
        description: CSV file download
        content:
          text/csv:
            schema:
              type: string
              format: binary
    ===
    """
    tracker_id = request.args.get("tracker_id", type=int)
    since = datetime.now(timezone.utc) - timedelta(days=1)
    q = TrackingHistory.query.filter(TrackingHistory.timestamp >= since)
    if tracker_id:
        q = q.filter_by(tracker_id=tracker_id)
    rows = [
        {
            "tracker_id": h.tracker_id,
            "pos_x": h.x,
            "pos_y": h.y,
            "pos_z": h.z,
            "timestamp": h.timestamp.isoformat() if h.timestamp else None,
        }
        for h in q.order_by(TrackingHistory.tracker_id, TrackingHistory.timestamp).all()
    ]
    return make_csv_response(rows, f"distance_history.csv")


@reports_bp.route("/full-export", methods=["GET"])
@jwt_required()
@require_permission(Permission.GENERATE_REPORT)
def full_export():
    """
    === A
    tags:
      - Reports
    summary: Full comprehensive report export
    description: Returns a comprehensive CSV export with all trackers, alerts, and history summary. Requires GENERATE_REPORT permission.
    security:
      - Bearer: []
    parameters:
      - in: query
        name: days
        schema:
          type: integer
          default: 7
        description: Number of past days to include
    responses:
      200:
        description: CSV file download
        content:
          text/csv:
            schema:
              type: string
              format: binary
    ===
    """
    days = int(request.args.get("days", 7))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    rows = []
    for t in Tracker.query.all():
        history = TrackingHistory.query.filter(
            TrackingHistory.tracker_id == t.id,
            TrackingHistory.timestamp >= since,
        ).all()
        dist = 0.0
        for i in range(1, len(history)):
            dx = history[i].x - history[i-1].x
            dy = history[i].y - history[i-1].y
            dist += (dx*dx + dy*dy) ** 0.5
        alert_count = Alert.query.filter(
            Alert.tracker_id == t.id,
            Alert.triggered_at >= since,
        ).count()
        rows.append({
            "tracker_id": t.id,
            "hardware_id": t.hardware_id,
            "assigned_name": t.assigned_name or "",
            "category": t.category_name,
            "asset_state": t.asset_state_name,
            "battery_level": t.battery_level,
            "position_records": len(history),
            "distance_m": round(dist, 2),
            "alert_count": alert_count,
            "first_seen": history[0].timestamp.isoformat() if history else "",
            "last_seen": history[-1].timestamp.isoformat() if history else "",
        })
    return make_csv_response(rows, f"full_report_{date_str}.csv")
