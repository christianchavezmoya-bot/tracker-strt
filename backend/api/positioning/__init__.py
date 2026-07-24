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
from backend.services.positioning_profile import get_positioning_profile

positioning_bp = Blueprint("positioning", __name__, url_prefix="/api/positioning")


@positioning_bp.route("/sources", methods=["GET"])
@jwt_required()
def positioning_sources():
    """
    Location Core status: which position sources feed live snapshots.
    """
    from backend.models import Tracker, WifiNode, HardwareConfig, ConnectionStatus
    live = db.session.query(PositionSnapshot).count()
    trackers = Tracker.query.count()
    anchors = WifiNode.query.count()
    hw = HardwareConfig.query.all()
    hw_connected = sum(1 for c in hw if int(getattr(c, "status", 0) or 0) == int(ConnectionStatus.CONNECTED))
    profile = get_positioning_profile(db.session)
    return jsonify({
        "location_core": True,
        "live_snapshots": live,
        "trackers": trackers,
        "anchors": anchors,
        "hardware_configs": len(hw),
        "hardware_connected": hw_connected,
        "positioning_profile": profile,
        "min_anchors_required": profile.get("min_anchors", 3),
        "positioning_mode": profile.get("positioning_mode"),
        "sources": [
            {"id": "ingestion", "label": "Hardware bridge / ingestion loop", "primary": True},
            {"id": "scanner", "label": "Wi‑Fi/BLE scanner → Trackers", "primary": True},
            {"id": "integrations", "label": "POST /api/integrations/positions", "primary": True},
            {"id": "uwb_demo", "label": "Legacy /api/uwb (deprecated)", "primary": False, "deprecated": True},
        ],
        "preferred_ui": "/",
        "setup_ui": "/?mode=setup",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Live position snapshots ────────────────────────────────────────────────────
@positioning_bp.route("/live", methods=["GET"])
@jwt_required()
def live_positions():
    """
    === A
    tags:
      - Positioning
    summary: Get all live positions
    description: Returns the latest position snapshot for every tracker.
    security:
      - Bearer: []
    responses:
      200:
        description: Live position data
        schema:
          type: object
          properties:
            positions:
              type: array
              items:
                type: object
                properties:
                  tracker_id: { type: integer }
                  x: { type: number }
                  y: { type: number }
                  z: { type: number }
                  accuracy: { type: number }
                  timestamp: { type: string, format: date-time }
            total: { type: integer }
            timestamp: { type: string, format: date-time }
    ===
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
    """
    === A
    tags:
      - Positioning
    summary: Get live position for one tracker
    description: Returns the latest position snapshot for a specific tracker.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: tracker_id
        required: true
        schema:
          type: integer
        description: Tracker ID
    responses:
      200:
        description: Tracker position
        schema:
          type: object
          properties:
            position:
              type: object
      404:
        description: Tracker not found
    ===
    """
    snap = db.session.query(PositionSnapshot).get(tracker_id)
    if not snap:
        return jsonify({"error": "Tracker not found"}), 404
    return jsonify({"position": snap.to_dict()})


# ── Position history ──────────────────────────────────────────────────────────
@positioning_bp.route("/history/<int:tracker_id>", methods=["GET"])
@jwt_required()
def tracker_history(tracker_id):
    """
    === A
    tags:
      - Positioning
    summary: Get position history for a tracker
    description: Returns historical position records for a specific tracker within a time range.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: tracker_id
        required: true
        schema:
          type: integer
        description: Tracker ID
      - in: query
        name: since
        schema:
          type: string
        description: ISO datetime string to filter records from (default: last 1 hour)
      - in: query
        name: limit
        schema:
          type: integer
          default: 1000
          maximum: 10000
        description: Maximum number of records to return
    responses:
      200:
        description: Position history records
        schema:
          type: object
          properties:
            tracker_id: { type: integer }
            history:
              type: array
              items:
                type: object
            count: { type: integer }
      400:
        description: Invalid since format
    ===
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
    === A
    tags:
      - Positioning
    summary: Export position history as CSV
    description: Returns a CSV file containing position history records for a specific tracker.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: tracker_id
        required: true
        schema:
          type: integer
        description: Tracker ID
      - in: query
        name: since
        schema:
          type: string
        description: ISO datetime string to filter records from
      - in: query
        name: limit
        schema:
          type: integer
          default: 10000
          maximum: 50000
        description: Maximum number of records to export
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
    """
    === A
    tags:
      - Positioning
    summary: Get positioning service stats
    description: Returns statistics from the history service including total records.
    security:
      - Bearer: []
    responses:
      200:
        description: Service statistics
        schema:
          type: object
      503:
        description: History service not running
    ===
    """
    svc = get_history_service()
    if svc:
        return jsonify(svc.get_stats())
    return jsonify({"error": "History service not running"}), 503


# ── Map context (regional default view) ───────────────────────────────────────
@positioning_bp.route("/map-context", methods=["GET"])
@jwt_required()
def map_context():
    """
    Site centre for regional map (OpenStreetMap) before mine grid is calibrated.
    Defaults to geographic centre of Australia when site_lat/site_lng are unset.
    """
    from backend.models import Setting

    def _float_setting(key: str, default: float) -> float:
        row = Setting.query.filter_by(key=key).first()
        if not row or row.value in (None, ""):
            return default
        try:
            return float(row.value)
        except (TypeError, ValueError):
            return default

    site_lat = _float_setting("site_lat", -25.2744)
    site_lng = _float_setting("site_lng", 133.7751)
    site_zoom = int(_float_setting("site_zoom", 5))
    site_location = Setting.query.filter_by(key="site_location").first()
    country = (site_location.value if site_location and site_location.value else "Australia").strip()

    from backend.services.floor_plan_mapper import get_floor_plan_mapper
    svc = get_floor_plan_mapper()
    cal = svc.get_calibration_status().get(0) or svc.get_calibration_status().get("0") or {}

    return jsonify({
        "site_lat": site_lat,
        "site_lng": site_lng,
        "site_zoom": site_zoom,
        "country": country,
        "is_mine_calibrated": bool(cal.get("calibrated")),
        "is_georef": bool(cal.get("is_georef")),
        "georef_points": cal.get("georef_points") or [],
    })


# ── Calibration ──────────────────────────────────────────────────────────────
@positioning_bp.route("/calibration", methods=["GET"])
@jwt_required()
def get_calibration():
    """
    === A
    tags:
      - Positioning
    summary: Get floor plan calibration status
    description: Returns the calibration status for the floor plan mapper.
    security:
      - Bearer: []
    responses:
      200:
        description: Calibration status
        schema:
          type: object
          properties:
            status: { type: object }
    ===
    """
    from backend.services.floor_plan_mapper import get_floor_plan_mapper
    svc = get_floor_plan_mapper()
    return jsonify({"status": svc.get_calibration_status()})


@positioning_bp.route("/calibration", methods=["POST"])
@jwt_required()
def add_calibration_point():
    """
    === A
    tags:
      - Positioning
    summary: Add a calibration point
    description: Adds a new calibration point for mapping pixel coordinates to real-world coordinates.
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - pixel_x
            - pixel_y
            - real_x
            - real_y
          properties:
            pixel_x:
              type: number
              description: X coordinate on floor plan image
            pixel_y:
              type: number
              description: Y coordinate on floor plan image
            real_x:
              type: number
              description: Real-world X coordinate in meters
            real_y:
              type: number
              description: Real-world Y coordinate in meters
            section_id:
              type: integer
              default: 0
              description: Section ID for multi-floor setups
    responses:
      200:
        description: Calibration point added
        schema:
          type: object
          properties:
            calibration_points: { type: array }
            is_calibrated: { type: boolean }
            calibration_error: { type: number }
      400:
        description: Missing required field
    ===
    """
    body = request.get_json() or {}

    from backend.services.floor_plan_mapper import get_floor_plan_mapper
    svc = get_floor_plan_mapper()
    section_id = int(body.get("section_id", 0))

    # Bulk save from map calibration wizard
    bulk = body.get("calibration_points")
    if isinstance(bulk, list) and len(bulk) >= 2:
        for pt in bulk:
            for f in ("pixel_x", "pixel_y", "real_x", "real_y"):
                if f not in pt:
                    return jsonify({"error": f"Missing field in point: {f}"}), 400
        mapper = svc.set_calibration_points(section_id, bulk)
        resp = {
            "calibration_points": svc.get_calibration_points(section_id),
            "is_calibrated": mapper.is_calibrated,
            "calibration_error": svc.calibration_error(section_id),
            "georef_points": svc.get_georef_points(section_id),
            "is_georef": svc.is_georef(section_id),
        }
        return jsonify(resp)

    georef_bulk = body.get("georef_points")
    if isinstance(georef_bulk, list) and len(georef_bulk) >= 2:
        for pt in georef_bulk:
            for f in ("pixel_x", "pixel_y", "lat", "lng"):
                if f not in pt:
                    return jsonify({"error": f"Missing georef field: {f}"}), 400
        svc.set_georef_points(section_id, georef_bulk)
        return jsonify({
            "georef_points": svc.get_georef_points(section_id),
            "is_georef": svc.is_georef(section_id),
            "calibration_points": svc.get_calibration_points(section_id),
            "is_calibrated": svc.is_calibrated(section_id),
        })

    required = ["pixel_x", "pixel_y", "real_x", "real_y"]
    for f in required:
        if f not in body:
            return jsonify({"error": f"Missing field: {f}"}), 400

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
