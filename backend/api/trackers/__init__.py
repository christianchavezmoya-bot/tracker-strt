"""Trackers API — Phase 2 stub (CRUD only, full logic in Phase 3)."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.models import Tracker, AuditLog, AssetState, TagType, DeviceCategory
from backend.utils.decorators import require_permission
from backend.services.rbac_service import Permission

trackers_bp = Blueprint("trackers", __name__, url_prefix="/api/trackers")


@trackers_bp.route("", methods=["GET"])
@jwt_required()
def list_trackers():
    """List all trackers with optional filters."""
    query = Tracker.query
    # Filters
    if request.args.get("category"):
        query = query.filter_by(category=int(request.args["category"]))
    if request.args.get("asset_state"):
        query = query.filter_by(asset_state=int(request.args["asset_state"]))
    if request.args.get("alert_status"):
        query = query.filter_by(alert_status=int(request.args["alert_status"]))
    if request.args.get("q"):
        q = f"%{request.args['q']}%"
        query = query.filter(
            (Tracker.hardware_id.ilike(q)) | (Tracker.assigned_name.ilike(q))
        )
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    pagination = query.order_by(Tracker.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [t.to_dict() for t in pagination.items],
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
        "pages": pagination.pages,
    })


@trackers_bp.route("", methods=["POST"])
@jwt_required()
@require_permission(Permission.MANAGE_TRACKER)
def create_tracker():
    body = request.get_json() or {}
    # Accept hardware_id / device_id / mac_address; coerce non-strings safely
    raw_id = body.get("hardware_id", body.get("device_id", body.get("mac_address", "")))
    hardware_id = str(raw_id or "").strip()
    if not hardware_id:
        return jsonify({"error": "hardware_id is required"}), 400
    if Tracker.query.filter_by(hardware_id=hardware_id).first():
        return jsonify({"error": "hardware_id already exists"}), 409

    def _as_int(val, default):
        if val is None or val == "":
            return int(default)
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)
        # Named enums e.g. "PERSONNEL"
        for enum_cls in (TagType, DeviceCategory):
            try:
                return int(enum_cls[str(val).upper()])
            except (KeyError, ValueError):
                pass
        try:
            return int(val)
        except (TypeError, ValueError):
            return int(default)

    name = body.get("assigned_name") or body.get("name")
    tracker = Tracker(
        hardware_id=hardware_id,
        assigned_name=name,
        tag_type=_as_int(body.get("tag_type", body.get("type")), TagType.PERSONNEL),
        category=_as_int(body.get("category"), DeviceCategory.PERSONNEL_TAG),
    )
    db.session.add(tracker)
    db.session.commit()
    AuditLog.log(action="tracker.create", user_id=int(get_jwt_identity()),
                 entity_type="Tracker", entity_id=tracker.id)
    return jsonify({"tracker": tracker.to_dict()}), 201


@trackers_bp.route("/<int:tracker_id>", methods=["GET"])
@jwt_required()
def get_tracker(tracker_id):
    tracker = Tracker.query.get_or_404(tracker_id)
    return jsonify({"tracker": tracker.to_dict()})


@trackers_bp.route("/<int:tracker_id>", methods=["PATCH"])
@jwt_required()
@require_permission(Permission.MANAGE_TRACKER)
def update_tracker(tracker_id):
    tracker = Tracker.query.get_or_404(tracker_id)
    body = request.get_json() or {}
    for field in ["assigned_name", "tag_type", "category", "icon_index",
                   "asset_state", "metadata_json"]:
        if field in body:
            setattr(tracker, field, body[field])
    db.session.commit()
    AuditLog.log(action="tracker.update", user_id=int(get_jwt_identity()),
                 entity_type="Tracker", entity_id=tracker.id)
    return jsonify({"tracker": tracker.to_dict()})


@trackers_bp.route("/<int:tracker_id>", methods=["DELETE"])
@jwt_required()
@require_permission(Permission.MANAGE_TRACKER)
def delete_tracker(tracker_id):
    tracker = Tracker.query.get_or_404(tracker_id)
    AuditLog.log(action="tracker.delete", user_id=int(get_jwt_identity()),
                 entity_type="Tracker", entity_id=tracker.id)
    db.session.delete(tracker)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200


@trackers_bp.route("/<int:tracker_id>/reassign", methods=["POST"])
@jwt_required()
@require_permission(Permission.MANAGE_TRACKER)
def reassign_tracker(tracker_id):
    """Reassign tracker to new hardware_id (when physical tag is replaced)."""
    tracker = Tracker.query.get_or_404(tracker_id)
    body = request.get_json() or {}
    new_hardware_id = str(body.get("hardware_id") or "").strip()
    if not new_hardware_id:
        return jsonify({"error": "hardware_id is required"}), 400
    if Tracker.query.filter_by(hardware_id=new_hardware_id).first():
        return jsonify({"error": "hardware_id already exists"}), 409
    old_id = tracker.hardware_id
    tracker.hardware_id = new_hardware_id
    db.session.commit()
    AuditLog.log(
        action="tracker.reassign",
        user_id=int(get_jwt_identity()),
        entity_type="Tracker", entity_id=tracker.id,
        details=f'{{"old_hardware_id": "{old_id}", "new_hardware_id": "{new_hardware_id}"}}',
    )
    return jsonify({"message": "Reassigned", "tracker": tracker.to_dict()})
