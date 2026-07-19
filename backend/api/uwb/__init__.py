"""
UWB / Positioning API — Phase 3 stub.
Integrates the reference/ code from tracker-strt.
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


@uwb_bp.route("/position", methods=["GET"])
@jwt_required()
def current_position():
    """Get current UWB-estimated position (from last measurement)."""
    from backend.api.uwb import _position_cache
    if not _position_cache:
        return jsonify({"error": "No position data yet"}), 503
    return jsonify(_position_cache)


@uwb_bp.route("/anchors", methods=["GET"])
@jwt_required()
def list_anchors():
    anchors = [{"id": k, "x": v[0], "y": v[1], "z": v[2]}
               for k, v in _uwb_pos.anchors.items()]
    return jsonify({"anchors": anchors})


@uwb_bp.route("/anchors", methods=["POST"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def configure_anchors():
    body = request.get_json() or {}
    anchors = body.get("anchors", [])
    _uwb_pos.anchors.clear()
    for a in anchors:
        _uwb_pos.add_anchor(a["id"], float(a["x"]), float(a["y"]), float(a.get("z", 0)))
    return jsonify({
        "status": "ok",
        "anchors_configured": len(_uwb_pos.anchors),
    })


@uwb_bp.route("/simulate", methods=["POST"])
@jwt_required()
def simulate():
    """Test positioning with simulated ranges."""
    body = request.get_json() or {}
    tag_x = float(body.get("tag_x", 25.0))
    tag_y = float(body.get("tag_y", 5.0))
    noise_std = float(body.get("noise_std", 0.1))

    ranges = simulate_uwb_ranges((tag_x, tag_y), _uwb_pos.anchors, noise_std)
    position = _uwb_pos.trilaterate_2d(ranges)

    if not position:
        return jsonify({"error": "Trilateration failed (need ≥3 anchors)"}), 400

    x, y = position
    accuracy = _uwb_pos.calculate_accuracy(position, ranges)
    x_s, y_s = _uwb_pos.smooth_position(position)

    return jsonify({
        "simulated_position": {"x": tag_x, "y": tag_y},
        "estimated_position": {"x": round(x, 3), "y": round(y, 3)},
        "smoothed_position": {"x": round(x_s, 3), "y": round(y_s, 3)},
        "accuracy_m": round(accuracy, 3),
        "ranges": {k: round(v, 3) for k, v in ranges.items()},
    })


# ── Live position cache (updated by background thread in Phase 3) ────────────
_position_cache = None


def update_position_cache(position_dict):
    global _position_cache
    _position_cache = position_dict
