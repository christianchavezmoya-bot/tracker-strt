"""Users Management API — Phase 8 stub."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.models import User, UserRole, AuditLog
from backend.utils.decorators import require_permission, admin_only
from backend.services.rbac_service import Permission

users_bp = Blueprint("users", __name__, url_prefix="/api/users")


@users_bp.route("", methods=["GET"])
@jwt_required()
@admin_only
def list_users():
    q = User.query
    if request.args.get("role"):
        q = q.filter_by(role=int(request.args["role"]))
    if request.args.get("is_active"):
        q = q.filter_by(is_active=request.args["is_active"] == "true")
    items = q.order_by(User.created_at.desc()).all()
    return jsonify({"items": [u.to_dict(include_email=True) for u in items],
                    "total": len(items)})


@users_bp.route("/<int:user_id>", methods=["PATCH"])
@jwt_required()
@admin_only
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    body = request.get_json() or {}
    for field in ["username", "display_name", "role", "is_active"]:
        if field in body:
            setattr(user, field, body[field])
    db.session.commit()
    AuditLog.log(action="user.update", user_id=int(get_jwt_identity()),
                 entity_type="User", entity_id=user.id)
    return jsonify({"user": user.to_dict(include_email=True)})


@users_bp.route("/<int:user_id>", methods=["DELETE"])
@jwt_required()
@admin_only
def deactivate_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == int(get_jwt_identity()):
        return jsonify({"error": "Cannot deactivate yourself"}), 400
    user.is_active = False
    db.session.commit()
    AuditLog.log(action="user.deactivate", user_id=int(get_jwt_identity()),
                 entity_type="User", entity_id=user.id)
    return jsonify({"message": "Deactivated"})
