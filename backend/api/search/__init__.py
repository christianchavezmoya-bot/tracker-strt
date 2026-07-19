"""Search API — Phase 8 enhanced."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from backend.models import Tracker, User, Zone, MapSection
from backend.models.tracker import AssetState, DeviceCategory
from backend.models.alert import Alert

search_bp = Blueprint("search", __name__, url_prefix="/api/search")


def _safe_enum(enum_cls, value, fallback="UNKNOWN"):
    try:
        return enum_cls(value).name
    except (ValueError, TypeError):
        return fallback


@search_bp.route("", methods=["GET"])
@jwt_required()
def global_search():
    """
    GET /api/search?q=<query>&type=<tracker|user|zone|section|alert|all>
    Returns results across all tracked entities.
    """
    q = request.args.get("q", "").strip()
    search_type = request.args.get("type", "all").lower()

    if not q or len(q) < 2:
        return jsonify({"results": _empty_results(), "query": q})

    like = f"%{q}%"
    results = _empty_results()

    if search_type in ("all", "tracker"):
        trackers = Tracker.query.filter(
            (Tracker.hardware_id.ilike(like)) | (Tracker.assigned_name.ilike(like))
        ).limit(20).all()
        results["trackers"] = [{
            "id": t.id,
            "hardware_id": t.hardware_id,
            "assigned_name": t.assigned_name,
            "category": _safe_enum(DeviceCategory, t.category),
            "asset_state": _safe_enum(AssetState, t.asset_state),
            "battery_level": t.battery_level,
            "alert_status": t.alert_status,
            "position": {"x": t.pos_x, "y": t.pos_y, "z": t.pos_z},
            "last_seen": t.updated_at.isoformat() if t.updated_at else None,
        } for t in trackers]

    if search_type in ("all", "user"):
        users = User.query.filter(
            (User.username.ilike(like)) | (User.display_name.ilike(like)) | (User.email.ilike(like))
        ).limit(10).all()
        results["users"] = [u.to_dict() for u in users]

    if search_type in ("all", "zone"):
        zones = Zone.query.filter(Zone.name.ilike(like)).limit(15).all()
        results["zones"] = [z.to_dict() for z in zones]

    if search_type in ("all", "section"):
        sections = MapSection.query.filter(MapSection.name.ilike(like)).limit(10).all()
        results["sections"] = [s.to_dict() for s in sections]

    if search_type in ("all", "alert"):
        alerts = Alert.query.filter(
            Alert.message.ilike(like),
        ).limit(10).all()
        results["alerts"] = [a.to_dict() for a in alerts]

    return jsonify({"results": results, "query": q})


def _empty_results():
    return {
        "trackers": [],
        "users": [],
        "zones": [],
        "sections": [],
        "alerts": [],
    }
