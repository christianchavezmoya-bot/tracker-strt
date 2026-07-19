"""
HOLO-RTLS — API Key management for integrations / scanners.
"""
import hashlib
import json
import secrets
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from backend.extensions import db
from backend.models import ApiKey, AuditLog
from backend.services.rbac_service import Permission
from backend.utils.decorators import require_permission

keys_bp = Blueprint("keys", __name__, url_prefix="/api/keys")


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@keys_bp.route("", methods=["GET"])
@jwt_required()
@require_permission(Permission.MANAGE_API_KEY)
def list_keys():
    keys = ApiKey.query.order_by(ApiKey.id.desc()).all()
    return jsonify({"items": [k.to_dict() for k in keys], "total": len(keys)})


@keys_bp.route("", methods=["POST"])
@jwt_required()
@require_permission(Permission.MANAGE_API_KEY)
def create_key():
    body = request.get_json() or {}
    name = (body.get("name") or "").strip() or "Integration key"
    raw = "holo_" + secrets.token_urlsafe(32)
    key = ApiKey(
        user_id=int(get_jwt_identity()),
        name=name,
        key_prefix=raw[:12],
        key_hash=_hash_key(raw),
        permissions=json.dumps(body.get("permissions") or ["scanner", "read"]),
        is_active=True,
    )
    db.session.add(key)
    db.session.commit()
    AuditLog.log(
        action="api_key.create",
        user_id=int(get_jwt_identity()),
        entity_type="ApiKey",
        entity_id=key.id,
        details=json.dumps({"name": name, "prefix": key.key_prefix}),
    )
    data = key.to_dict()
    data["secret"] = raw  # shown once
    return jsonify({"key": data, "message": "Store this secret now — it will not be shown again"}), 201


@keys_bp.route("/<int:key_id>", methods=["DELETE"])
@jwt_required()
@require_permission(Permission.MANAGE_API_KEY)
def revoke_key(key_id):
    key = ApiKey.query.get_or_404(key_id)
    key.is_active = False
    db.session.commit()
    AuditLog.log(
        action="api_key.revoke",
        user_id=int(get_jwt_identity()),
        entity_type="ApiKey",
        entity_id=key.id,
    )
    return jsonify({"message": "Revoked", "key": key.to_dict()})


@keys_bp.route("/<int:key_id>/rotate", methods=["POST"])
@jwt_required()
@require_permission(Permission.MANAGE_API_KEY)
def rotate_key(key_id):
    key = ApiKey.query.get_or_404(key_id)
    raw = "holo_" + secrets.token_urlsafe(32)
    key.key_prefix = raw[:12]
    key.key_hash = _hash_key(raw)
    key.is_active = True
    key.last_used_at = None
    db.session.commit()
    data = key.to_dict()
    data["secret"] = raw
    return jsonify({"key": data, "message": "Key rotated — store the new secret now"})
