"""Search API — Phase 2 stub."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from backend.models import Tracker, User

search_bp = Blueprint("search", __name__, url_prefix="/api/search")


@search_bp.route("", methods=["GET"])
@jwt_required()
def global_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify({"results": [], "query": q})
    like = f"%{q}%"
    results = {"trackers": [], "users": []}

    # Search trackers
    trackers = Tracker.query.filter(
        (Tracker.hardware_id.ilike(like)) | (Tracker.assigned_name.ilike(like))
    ).limit(20).all()
    results["trackers"] = [t.to_dict() for t in trackers]

    # Search users
    users = User.query.filter(
        (User.username.ilike(like)) | (User.display_name.ilike(like)) | (User.email.ilike(like))
    ).limit(10).all()
    results["users"] = [u.to_dict() for u in users]

    return jsonify({"results": results, "query": q})
