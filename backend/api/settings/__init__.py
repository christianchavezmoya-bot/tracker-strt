"""Settings API — Phase 9 (floor plan manager + enhanced)."""
from flask import Blueprint, request, jsonify, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
import os, imghdr, json, uuid

from backend.extensions import db
from backend.models import Setting, BusinessLogo, AuditLog, SettingScope
from backend.models.tracker import MapSection
from backend.utils.decorators import require_permission, admin_only
from backend.services.rbac_service import Permission
from backend import config

settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")

ALLOWED_LOGO_EXT = config.ALLOWED_LOGO_EXTENSIONS
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "tiff", "bmp"}
FLOOR_PLAN_DIR = config.BASE_DIR / "frontend" / "static" / "assets" / "floor-plans"
FLOOR_PLAN_DIR.mkdir(parents=True, exist_ok=True)
MAX_IMAGE_MB = 20


def allowed_ext(filename, allowed_set):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_set


@settings_bp.route("", methods=["GET"])
@jwt_required()
def list_settings():
    """
    === A
    tags:
      - Settings
    summary: List all settings
    description: Returns all settings with optional filtering by scope.
    security:
      - Bearer: []
    parameters:
      - in: query
        name: scope
        schema:
          type: integer
        description: Filter by setting scope
    responses:
      200:
        description: List of settings
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
    ===
    """
    scope = request.args.get("scope")
    q = Setting.query
    if scope:
        q = q.filter_by(scope=int(scope))
    items = q.all()
    return jsonify({"items": [s.to_dict() for s in items]})


@settings_bp.route("/<key>", methods=["GET"])
@jwt_required()
def get_setting(key):
    """
    === A
    tags:
      - Settings
    summary: Get a setting by key
    description: Returns a specific setting by its key.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: key
        required: true
        schema:
          type: string
        description: Setting key
    responses:
      200:
        description: Setting value
        schema:
          type: object
          properties:
            setting: { type: object }
      404:
        description: Setting not found
    ===
    """
    setting = Setting.query.filter_by(key=key).first()
    if not setting:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"setting": setting.to_dict()})


@settings_bp.route("/<key>", methods=["PUT"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def update_setting(key):
    """
    === A
    tags:
      - Settings
    summary: Update a setting
    description: Updates a setting value or creates it if it doesn't exist. Requires EDIT_SETTINGS permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: key
        required: true
        schema:
          type: string
        description: Setting key
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - value
          properties:
            value:
              type: string
              description: New value for the setting
    responses:
      200:
        description: Setting updated
        schema:
          type: object
          properties:
            setting: { type: object }
      404:
        description: Not found or no permission
    ===
    """
    setting = Setting.query.filter_by(key=key).first()
    if not setting:
        user_id = int(get_jwt_identity())
        from backend.models import User
        user = db.session.get(User, user_id)
        if not user or user.role != 3:
            return jsonify({"error": "Admin permission required"}), 403
        setting = Setting(key=key)
        db.session.add(setting)
    body = request.get_json() or {}
    if "value" in body:
        setting.set_typed_value(body["value"])
    setting.updated_by_id = int(get_jwt_identity())
    db.session.commit()
    AuditLog.log(action="settings.update", user_id=int(get_jwt_identity()),
                 entity_type="Setting", entity_id=setting.id,
                 details=f'{{"key": "{key}"}}')
    return jsonify({"setting": setting.to_dict()})


@settings_bp.route("/logo", methods=["POST"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def upload_logo():
    """
    === A
    tags:
      - Settings
    summary: Upload business logo
    description: Uploads a new business logo image. Replaces existing logo if one exists. Requires EDIT_SETTINGS permission.
    security:
      - Bearer: []
    parameters:
      - in: formData
        name: logo
        required: true
        type: file
        description: Logo image file (PNG, JPG, SVG, or WebP)
    responses:
      200:
        description: Logo uploaded
        schema:
          type: object
          properties:
            logo: { type: object }
            url: { type: string }
      400:
        description: No file provided or invalid file type
    ===
    """
    file = request.files.get("logo")
    if not file:
        return jsonify({"error": "No file provided"}), 400
    if not allowed_ext(file.filename, ALLOWED_LOGO_EXT):
        return jsonify({"error": "Invalid file type"}), 400
    filename = secure_filename(file.filename)
    # Unique name: logo_YYYYMMDD_<original>
    from datetime import datetime
    unique_name = f"logo_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
    filepath = config.UPLOAD_DIR / unique_name
    file.save(str(filepath))
    size = os.path.getsize(filepath)
    if size > config.MAX_LOGO_SIZE_MB * 1024 * 1024:
        os.remove(filepath)
        return jsonify({"error": f"File too large (max {config.MAX_LOGO_SIZE_MB}MB)"}), 400
    # Update or create logo record
    logo = BusinessLogo.query.first()
    if logo:
        # Delete old file
        old_path = config.UPLOAD_DIR / logo.filename
        if old_path.exists():
            os.remove(str(old_path))
        logo.filename = unique_name
        logo.original_name = filename
        logo.mime_type = file.content_type
        logo.size_bytes = size
        logo.uploaded_by_id = int(get_jwt_identity())
    else:
        logo = BusinessLogo(
            filename=unique_name, original_name=filename,
            mime_type=file.content_type, size_bytes=size,
            uploaded_by_id=int(get_jwt_identity()),
        )
        db.session.add(logo)
    db.session.commit()
    AuditLog.log(action="settings.logo_upload", user_id=int(get_jwt_identity()),
                 entity_type="BusinessLogo", entity_id=logo.id)
    return jsonify({"logo": logo.to_dict(), "url": f"/static/assets/logos/{unique_name}"})


@settings_bp.route("/logo", methods=["GET"])
def get_logo():
    """
    === A
    tags:
      - Settings
    summary: Get business logo
    description: Returns the current business logo metadata and URL.
    responses:
      200:
        description: Logo data
        schema:
          type: object
          properties:
            logo: { type: object, nullable: true }
            url: { type: string }
    ===
    """
    logo = BusinessLogo.query.first()
    if not logo:
        return jsonify({"logo": None})
    return jsonify({
        "logo": logo.to_dict(),
        "url": f"/static/assets/logos/{logo.filename}",
    })


# ── Floor Plan Management ────────────────────────────────────────────────────

@settings_bp.route("/floor-plans", methods=["GET"])
@jwt_required()
def list_floor_plans():
    """
    List all uploaded floor plan images with calibration status.
    """
    sections = MapSection.query.order_by(MapSection.z_index).all()
    return jsonify({"items": [s.to_dict() for s in sections]})


@settings_bp.route("/floor-plans", methods=["POST"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def upload_floor_plan():
    """
    Upload a floor plan image (PNG/JPG/WebP) and optionally create a MapSection.
    """
    file = request.files.get("image")
    if not file:
        return jsonify({"error": "No image file provided"}), 400
    if not allowed_ext(file.filename, ALLOWED_IMAGE_EXT):
        return jsonify({"error": f"Invalid file type. Allowed: {', '.join(ALLOWED_IMAGE_EXT)}"}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_name = f"fp_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = FLOOR_PLAN_DIR / unique_name
    file.save(str(filepath))

    size = os.path.getsize(filepath)
    if size > MAX_IMAGE_MB * 1024 * 1024:
        os.remove(filepath)
        return jsonify({"error": f"File too large (max {MAX_IMAGE_MB}MB)"}), 400

    body = request.form or {}
    name = body.get("name", "").strip() or f"Floor Plan {unique_name}"
    section = MapSection(
        name=name,
        image_url=f"/static/assets/floor-plans/{unique_name}",
        color_hex=body.get("color_hex", "#00e5ff"),
        z_index=int(body.get("z_index", 0)),
        is_visible=body.get("is_visible", "true").lower() != "false",
        is_restricted=False,
    )
    db.session.add(section)
    db.session.commit()
    AuditLog.log(action="floor_plan.upload", user_id=int(get_jwt_identity()),
                 entity_type="MapSection", entity_id=section.id)
    return jsonify({"section": section.to_dict()}), 201


@settings_bp.route("/floor-plans/<int:section_id>", methods=["PATCH"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def update_floor_plan(section_id):
    """
    Update floor plan metadata (name, visibility, color).
    """
    section = MapSection.query.get_or_404(section_id)
    body = request.get_json() or {}
    for field in ["name", "color_hex", "z_index", "is_visible", "is_restricted"]:
        if field in body:
            setattr(section, field, body[field])
    db.session.commit()
    AuditLog.log(action="floor_plan.update", user_id=int(get_jwt_identity()),
                 entity_type="MapSection", entity_id=section.id)
    return jsonify({"section": section.to_dict()})


@settings_bp.route("/floor-plans/<int:section_id>", methods=["DELETE"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def delete_floor_plan(section_id):
    """
    Delete a floor plan and its image file.
    """
    section = MapSection.query.get_or_404(section_id)
    # Remove image file
    if section.image_url:
        img_path = config.BASE_DIR / "frontend" / "static" / section.image_url.lstrip("/")
        if img_path.exists():
            os.remove(str(img_path))
    AuditLog.log(action="floor_plan.delete", user_id=int(get_jwt_identity()),
                 entity_type="MapSection", entity_id=section.id)
    db.session.delete(section)
    db.session.commit()
    return jsonify({"message": "Floor plan deleted"})


# ── System Status ────────────────────────────────────────────────────────────────

@settings_bp.route("/status", methods=["GET"])
@jwt_required()
def system_status():
    """
    GET /api/settings/status
    Returns system health, DB stats, ingestion status, and uptime info.
    No special permission required — for monitoring dashboards.
    """
    from datetime import datetime, timezone
    from backend.models.positioning import TrackingHistory, PositionSnapshot
    from backend.models import Tracker, Alert
    from backend.services.history_service import get_history_service

    hist_svc = get_history_service()
    hist_stats = hist_svc.get_stats() if hist_svc else {}

    total_trackers = Tracker.query.count()
    active_trackers = Tracker.query.filter_by(asset_state=1).count()
    total_alerts = Alert.query.count()
    active_alerts = Alert.query.filter_by(state=1).count()
    total_history = TrackingHistory.query.count()
    total_snapshots = PositionSnapshot.query.count()

    ingestion_running = False
    try:
        from backend.services.ingestion_loop import get_ingestion_loop
        loop = get_ingestion_loop()
        ingestion_running = bool(loop and loop.is_alive())
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "bridge_online": ingestion_running,
        "ingestion_running": ingestion_running,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trackers": {
            "total": total_trackers,
            "active": active_trackers,
        },
        "alerts": {
            "total": total_alerts,
            "active": active_alerts,
        },
        "history": {
            "total_records": total_history,
            "total_snapshots": total_snapshots,
            "retention_days": hist_stats.get("retention_days", "?"),
            "total_written": hist_stats.get("total_written", 0),
            "total_pruned": hist_stats.get("total_pruned", 0),
            "buffer_size": hist_stats.get("buffer_size", 0),
        },
    })
