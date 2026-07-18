"""Settings API — Phase 7 stub."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
import os, imghdr

from backend.extensions import db
from backend.models import Setting, BusinessLogo, AuditLog, SettingScope
from backend.utils.decorators import require_permission, admin_only
from backend.services.rbac_service import Permission
from backend import config

settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")

ALLOWED_EXTENSIONS = config.ALLOWED_LOGO_EXTENSIONS


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@settings_bp.route("", methods=["GET"])
@jwt_required()
def list_settings():
    scope = request.args.get("scope")
    q = Setting.query
    if scope:
        q = q.filter_by(scope=int(scope))
    items = q.all()
    return jsonify({"items": [s.to_dict() for s in items]})


@settings_bp.route("/<key>", methods=["GET"])
@jwt_required()
def get_setting(key):
    setting = Setting.query.filter_by(key=key).first()
    if not setting:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"setting": setting.to_dict()})


@settings_bp.route("/<key>", methods=["PUT"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def update_setting(key):
    setting = Setting.query.filter_by(key=key).first()
    if not setting:
        if not request.current_user.role == 3:
            return jsonify({"error": "Not found or no permission"}), 404
        body = request.get_json() or {}
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
    file = request.files.get("logo")
    if not file:
        return jsonify({"error": "No file provided"}), 400
    if not allowed_file(file.filename):
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
    logo = BusinessLogo.query.first()
    if not logo:
        return jsonify({"logo": None})
    return jsonify({
        "logo": logo.to_dict(),
        "url": f"/static/assets/logos/{logo.filename}",
    })
