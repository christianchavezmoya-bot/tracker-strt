"""
UWB / Positioning API — LEGACY DEMO (deprecated).

Prefer Location Core:
  - Live positions: GET /api/positioning/live, SSE /api/stream/positions
  - Hardware profiles: /api/hardware + mock_data / UWB bridges
  - External inject: POST /api/integrations/positions

These routes remain for compatibility and lab simulation only.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from backend.utils.decorators import require_permission
from backend.services.rbac_service import Permission

# Import reference modules directly (they are part of this repo now)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "reference"))
from uwb_positioning import UWBPositioning, simulate_uwb_ranges
from uwb_serial_reader import create_mock_reader

uwb_bp = Blueprint("uwb", __name__, url_prefix="/api/uwb")

# ── Singleton UWB engine ──────────────────────────────────────────────────────
_uwb_pos = UWBPositioning(num_anchors=4)
_uwb_pos.add_anchor("anchor_0", 0.0, 0.0, 0.0)
_uwb_pos.add_anchor("anchor_1", 50.0, 0.0, 0.0)
_uwb_pos.add_anchor("anchor_2", 100.0, 0.0, 0.0)
_uwb_pos.add_anchor("anchor_3", 50.0, 10.0, 0.0)
_position_cache = {}

_DEPRECATED = {
    "deprecated": True,
    "message": "Use /api/positioning/* and /api/hardware — /api/uwb is a legacy demo",
    "successor": "/api/positioning/live",
}


@uwb_bp.after_request
def _uwb_deprecation_headers(response):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Sat, 01 Aug 2026 00:00:00 GMT"
    response.headers["Link"] = '</api/positioning/live>; rel="successor-version"'
    response.headers["X-HOLO-Deprecated"] = "api/uwb → api/positioning"
    return response


@uwb_bp.route("/position", methods=["GET"])
@jwt_required()
def current_position():
    """
    ---
    deprecated: true
    tags: [UWB-Deprecated]
    summary: Legacy demo position (deprecated)
    ---
    """
    if not _position_cache:
        return jsonify({"error": "No position data yet", **_DEPRECATED}), 503
    out = dict(_position_cache)
    out.update(_DEPRECATED)
    return jsonify(out)


@uwb_bp.route("/anchors", methods=["GET"])
@jwt_required()
def list_anchors():
    """
    ---
    deprecated: true
    tags: [UWB-Deprecated]
    ---
    """
    anchors = [{"id": k, "x": v[0], "y": v[1], "z": v[2]}
               for k, v in _uwb_pos.anchors.items()]
    return jsonify({"anchors": anchors, **_DEPRECATED})


@uwb_bp.route("/anchors", methods=["POST"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def configure_anchors():
    """
    ---
    deprecated: true
    tags: [UWB-Deprecated]
    ---
    """
    body = request.get_json() or {}
    anchors = body.get("anchors", [])
    _uwb_pos.anchors.clear()
    for a in anchors:
        _uwb_pos.add_anchor(a["id"], float(a["x"]), float(a["y"]), float(a.get("z", 0)))
    return jsonify({"message": "Anchors configured (legacy)", "count": len(anchors), **_DEPRECATED})


@uwb_bp.route("/simulate", methods=["POST"])
@jwt_required()
def simulate():
    """
    ---
    deprecated: true
    tags: [UWB-Deprecated]
    summary: Lab trilateration simulate (deprecated)
    ---
    """
    body = request.get_json() or {}
    tag_x = float(body.get("tag_x", 25))
    tag_y = float(body.get("tag_y", 5))
    noise = float(body.get("noise_std", 0.1))
    ranges = simulate_uwb_ranges(_uwb_pos.anchors, tag_x, tag_y, 0.0, noise_std=noise)
    est = _uwb_pos.trilaterate(ranges)
    smoothed = _uwb_pos.smooth(est) if est else None
    result = {
        "estimated": est,
        "smoothed": smoothed,
        "ranges": ranges,
        **_DEPRECATED,
    }
    if smoothed:
        update_position_cache({"x": smoothed[0], "y": smoothed[1], "z": smoothed[2] if len(smoothed) > 2 else 0})
    return jsonify(result)


def update_position_cache(pos: dict):
    global _position_cache
    _position_cache = pos
