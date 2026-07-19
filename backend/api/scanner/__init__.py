"""
HOLO-RTLS — Scanner / Detection API
Receives WiFi + BLE scan data from distributed scanner nodes,
computes positions via trilateration, and exposes live device positions.
"""
import logging
import os
import uuid
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity

from backend.extensions import db
from backend.models.detection import (
    FloorPlan, WifiAnchor, DetectionEvent, TrackedDevice,
    SignalType, AnchorStatus, DeviceType,
)
from backend.services.wifi_positioning import WifiPositioningService

logger = logging.getLogger(__name__)
scanner_bp = Blueprint("scanner", __name__, url_prefix="/api/scanner")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _get_pos_service() -> WifiPositioningService:
    return WifiPositioningService(db.session)


# ── Detection ingestion ───────────────────────────────────────────────────────
@scanner_bp.route("/detections", methods=["POST"])
def ingest_detections():
    """
    Receive a batch of WiFi/BLE detection events from a scanner node.
    Scanner POSTs its own MAC + list of {mac_address, rssi, signal_type, ssid?, adv_name?, channel?}.

    No JWT required — scanner nodes authenticate via a shared API key header.
    In production, use mutual TLS or a per-node JWT.
    """
    api_key = request.headers.get("X-Scanner-Key", "")
    expected_key = os.getenv("SCANNER_API_KEY", "scanner-dev-key")
    if api_key != expected_key and current_app.config.get("TESTING") is not True:
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json() or {}
    anchor_mac = body.get("anchor_mac", "").upper()
    detections = body.get("detections", [])

    if not anchor_mac or not detections:
        return jsonify({"error": "anchor_mac and detections are required"}), 400

    if not isinstance(detections, list):
        return jsonify({"error": "detections must be a list"}), 400

    pos_svc = _get_pos_service()
    n = pos_svc.process_scan_batch(anchor_mac, detections)
    fixes = pos_svc.compute_all_positions()

    return jsonify({
        "ok": True,
        "anchor_mac": anchor_mac,
        "detections_received": len(detections),
        "positions_computed": len(fixes),
        "timestamp": datetime.utcnow().isoformat(),
    })


# ── Anchor management ─────────────────────────────────────────────────────────
@scanner_bp.route("/anchors", methods=["GET"])
@jwt_required()
def list_anchors():
    """List all registered scanner anchors."""
    anchors = db.session.query(WifiAnchor).all()
    return jsonify({
        "items": [a.to_dict() for a in anchors],
        "total": len(anchors),
    })


@scanner_bp.route("/anchors", methods=["POST"])
@jwt_required()
def register_anchor():
    """
    Register (or update) a scanner anchor.
    If the anchor already exists, update its name / floor_plan association.
    """
    body = request.get_json() or {}
    mac  = body.get("mac_address", "").strip().upper()
    if not mac:
        return jsonify({"error": "mac_address is required"}), 400

    anchor = db.session.query(WifiAnchor).filter_by(mac_address=mac).first()
    created = False
    if not anchor:
        anchor = WifiAnchor(mac_address=mac)
        db.session.add(anchor)
        created = True

    if body.get("name"):
        anchor.name = body["name"]
    if body.get("floor_plan_id"):
        anchor.floor_plan_id = int(body["floor_plan_id"])

    db.session.commit()
    return jsonify({
        "anchor": anchor.to_dict(),
        "created": created,
    }), 201 if created else 200


@scanner_bp.route("/anchors/<int:anchor_id>", methods=["GET"])
@jwt_required()
def get_anchor(anchor_id):
    anchor = db.session.query(WifiAnchor).get(anchor_id)
    if not anchor:
        return jsonify({"error": "Anchor not found"}), 404
    return jsonify({"anchor": anchor.to_dict()})


@scanner_bp.route("/anchors/<int:anchor_id>", methods=["PATCH"])
@jwt_required()
def update_anchor(anchor_id):
    """
    Update anchor position (pixel or real-world) and calibration.
    Typical flow:
      1. Admin places anchor on floor plan UI → sets pixel_x, pixel_y
      2. Admin calibrates → sets real_x, real_y via calibration point
      3. Admin calibrates TX power → sets tx_power
    """
    anchor = db.session.query(WifiAnchor).get(anchor_id)
    if not anchor:
        return jsonify({"error": "Anchor not found"}), 404

    body = request.get_json() or {}
    for field in ("name", "pixel_x", "pixel_y", "real_x", "real_y", "real_z",
                  "tx_power", "floor_plan_id"):
        if field in body:
            val = body[field]
            if val is not None:
                val = float(val) if field not in ("name",) else val
            setattr(anchor, field, val)

    if "status" in body:
        anchor.status = int(body["status"])

    db.session.commit()
    return jsonify({"anchor": anchor.to_dict()})


@scanner_bp.route("/anchors/<int:anchor_id>/calibrate", methods=["POST"])
@jwt_required()
def calibrate_anchor(anchor_id):
    """
    Calibrate anchor TX power using a reference device at a known distance.
    Body: { "reference_rssi": -55.0, "reference_distance": 1.0 }
    Computes: tx_power = reference_rssi + 10 * n * log10(reference_distance)
    """
    anchor = db.session.query(WifiAnchor).get(anchor_id)
    if not anchor:
        return jsonify({"error": "Anchor not found"}), 404

    body = request.get_json() or {}
    ref_rssi = body.get("reference_rssi")
    ref_dist = body.get("reference_distance", 1.0)

    if ref_rssi is None:
        return jsonify({"error": "reference_rssi is required"}), 400

    import math
    n = float(body.get("path_loss_exp", 2.5))
    tx_power = ref_rssi + 10 * n * math.log10(max(ref_dist, 0.01))

    anchor.tx_power = round(tx_power, 2)
    db.session.commit()

    return jsonify({
        "anchor": anchor.to_dict(),
        "calibration": {
            "tx_power": anchor.tx_power,
            "reference_rssi": ref_rssi,
            "reference_distance": ref_dist,
            "path_loss_exp": n,
        },
    })


# ── Floor plan management ─────────────────────────────────────────────────────
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(__file__)))), "uploads", "floorplans")


@scanner_bp.route("/floorplans", methods=["GET"])
@jwt_required()
def list_floorplans():
    fps = db.session.query(FloorPlan).order_by(FloorPlan.level).all()
    return jsonify({
        "items": [fp.to_dict() for fp in fps],
        "total": len(fps),
    })


@scanner_bp.route("/floorplans", methods=["POST"])
@jwt_required()
def create_floorplan():
    """Create a new floor plan record (image upload done separately)."""
    body = request.get_json() or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    fp = FloorPlan(
        name=name,
        level=int(body.get("level", 0)),
        real_width=body.get("real_width"),
        real_height=body.get("real_height"),
    )
    db.session.add(fp)
    db.session.commit()
    return jsonify({"floor_plan": fp.to_dict()}), 201


@scanner_bp.route("/floorplans/<int:fp_id>", methods=["GET"])
@jwt_required()
def get_floorplan(fp_id):
    fp = db.session.query(FloorPlan).get(fp_id)
    if not fp:
        return jsonify({"error": "Floor plan not found"}), 404
    return jsonify({"floor_plan": fp.to_dict()})


@scanner_bp.route("/floorplans/<int:fp_id>", methods=["PATCH"])
@jwt_required()
def update_floorplan(fp_id):
    fp = db.session.query(FloorPlan).get(fp_id)
    if not fp:
        return jsonify({"error": "Floor plan not found"}), 404

    body = request.get_json() or {}
    for field in ("name", "level", "real_width", "real_height", "image_url",
                   "calibration_json", "is_active"):
        if field in body:
            setattr(fp, field, body[field])

    db.session.commit()
    return jsonify({"floor_plan": fp.to_dict()})


@scanner_bp.route("/floorplans/<int:fp_id>/upload", methods=["POST"])
@jwt_required()
def upload_floorplan_image(fp_id):
    """
    Upload a floor plan image (PNG / JPG) for a floor plan record.
    Image is saved to uploads/floorplans/{fp_id}_{uuid}.{ext}
    """
    fp = db.session.query(FloorPlan).get(fp_id)
    if not fp:
        return jsonify({"error": "Floor plan not found"}), 404

    if "image" not in request.files:
        return jsonify({"error": "No image file in request"}), 400

    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
        return jsonify({"error": "Unsupported image type"}), 400

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename = f"{fp_id}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    # Store relative path
    rel_url = f"/uploads/floorplans/{filename}"
    fp.image_url = rel_url
    db.session.commit()

    return jsonify({
        "floor_plan": fp.to_dict(),
        "image_url": rel_url,
    })


# ── Tracked devices ───────────────────────────────────────────────────────────
@scanner_bp.route("/devices", methods=["GET"])
@jwt_required()
def list_devices():
    """
    List all tracked devices with last known positions.
    Filter by: ?active=1&floor_plan_id=1&q=mac_or_name
    """
    query = db.session.query(TrackedDevice)

    if request.args.get("active") in ("1", "true"):
        since = datetime.utcnow()
        from datetime import timedelta
        cutoff = since - timedelta(seconds=int(request.args.get("active_within_sec", 120)))
        query = query.filter(TrackedDevice.last_seen >= cutoff, TrackedDevice.is_active == True)
    elif request.args.get("q"):
        q = f"%{request.args['q']}%"
        query = query.filter(
            (TrackedDevice.mac_address.ilike(q)) | (TrackedDevice.name.ilike(q))
        )

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    pagination = query.order_by(TrackedDevice.last_seen.desc()).paginate(
        page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [d.to_dict() for d in pagination.items],
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
        "pages": pagination.pages,
    })


@scanner_bp.route("/devices/<mac_address>", methods=["GET"])
@jwt_required()
def get_device(mac_address):
    """Get details for a specific device by MAC."""
    dev = db.session.query(TrackedDevice).filter(
        TrackedDevice.mac_address == mac_address.upper()
    ).first()
    if not dev:
        return jsonify({"error": "Device not found"}), 404
    return jsonify({"device": dev.to_dict()})


@scanner_bp.route("/devices/<mac_address>", methods=["PATCH"])
@jwt_required()
def update_device(mac_address):
    """
    Create or update a tracked device (upsert by MAC).
    Returns the device document.
    """
    dev = db.session.query(TrackedDevice).filter(
        TrackedDevice.mac_address == mac_address.upper()
    ).first()
    if not dev:
        dev = TrackedDevice(mac_address=mac_address.upper())
        db.session.add(dev)

    body = request.get_json() or {}
    if "name" in body:
        dev.name = body["name"]
    if "device_type" in body:
        dev.device_type = int(body["device_type"])
    if "notes" in body:
        dev.notes = body["notes"]
    if "is_active" in body:
        dev.is_active = bool(body["is_active"])

    db.session.commit()
    return jsonify({"device": dev.to_dict()})


# ── Live positions ────────────────────────────────────────────────────────────
@scanner_bp.route("/positions/live", methods=["GET"])
@jwt_required()
def live_positions():
    """
    Return the most recent computed positions for all active tracked devices.
    Combines TrackedDevice (last known) + PositionSnapshot (freshest) data.
    """
    pos_svc = _get_pos_service()
    floor_plan_id = request.args.get("floor_plan_id", type=int)

    devices = pos_svc.get_active_devices(floor_plan_id=floor_plan_id, since_seconds=120.0)
    return jsonify({
        "devices": devices,
        "total": len(devices),
        "timestamp": datetime.utcnow().isoformat(),
    })


@scanner_bp.route("/positions/refresh", methods=["POST"])
@jwt_required()
def refresh_positions():
    """
    Force a full trilateration pass — useful after anchor config changes.
    Returns the newly computed positions.
    """
    pos_svc = _get_pos_service()
    body = request.get_json() or {}
    floor_plan_id = body.get("floor_plan_id")
    fixes = pos_svc.compute_all_positions(floor_plan_id=floor_plan_id)
    return jsonify({
        "positions": [
            {"mac_address": f.mac_address, "x": f.x, "y": f.y, "z": f.z,
             "accuracy": f.accuracy, "anchors_used": f.anchors_used}
            for f in fixes
        ],
        "count": len(fixes),
    })
