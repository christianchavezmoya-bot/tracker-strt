"""External position inject (I04) — JWT or X-API-Key."""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

from backend.extensions import db
from backend.models import Tracker

inject_bp = Blueprint("inject", __name__, url_prefix="/api/integrations")


def _auth_ok():
    """Accept JWT Bearer or previously-validated request.api_key from middleware."""
    if getattr(request, "api_key", None):
        return True
    try:
        verify_jwt_in_request(optional=True)
        if get_jwt_identity():
            return True
    except Exception:
        pass
    return False


@inject_bp.route("/positions", methods=["POST"])
def inject_positions():
    """
    Inject one or more positions from an external IPS.
    Body: { "positions": [ { "hardware_id": "...", "x": 1.0, "y": 2.0, "z": 0 } ] }
    Auth: Authorization Bearer JWT OR X-API-Key header.
    """
    if not _auth_ok():
        # If API key middleware already 401'd invalid keys; here missing both
        if not request.headers.get("X-API-Key") and not request.headers.get("Authorization"):
            return jsonify({"error": "Authorization required (JWT or X-API-Key)"}), 401
        if not getattr(request, "api_key", None):
            return jsonify({"error": "Authorization required (JWT or X-API-Key)"}), 401

    body = request.get_json() or {}
    items = body.get("positions") or ([body] if body.get("hardware_id") or body.get("tracker_id") else [])
    if not items:
        return jsonify({"error": "positions array required"}), 400

    updated = 0
    for item in items:
        tracker = None
        if item.get("tracker_id"):
            tracker = Tracker.query.get(int(item["tracker_id"]))
        elif item.get("hardware_id"):
            tracker = Tracker.query.filter_by(hardware_id=str(item["hardware_id"])).first()
        if not tracker:
            continue
        if "x" in item:
            tracker.pos_x = float(item["x"])
        if "y" in item:
            tracker.pos_y = float(item["y"])
        if "z" in item:
            tracker.pos_z = float(item.get("z") or 0)
        tracker.last_seen = datetime.now(timezone.utc)
        updated += 1

        # Persist history + SSE if services available
        try:
            from backend.services.history_service import get_history_service
            hist = get_history_service()
            if hist:
                hist.write_position(tracker.id, tracker.pos_x, tracker.pos_y, tracker.pos_z or 0)
        except Exception:
            pass
        try:
            from backend.services.ingestion_loop import get_ingestion_loop
            loop = get_ingestion_loop()
            if loop:
                loop._broadcast_sse({
                    "type": "position",
                    "tracker_id": tracker.id,
                    "hardware_id": tracker.hardware_id,
                    "x": tracker.pos_x,
                    "y": tracker.pos_y,
                    "z": tracker.pos_z,
                })
        except Exception:
            pass

    db.session.commit()
    return jsonify({"updated": updated}), 200
