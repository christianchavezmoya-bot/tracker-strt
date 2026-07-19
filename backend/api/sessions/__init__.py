"""Sessions API — list / revoke login sessions."""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from backend.extensions import db
from backend.models import User, UserSession, AuditLog, UserRole
from backend.services.rbac_service import Permission
from backend.utils.decorators import require_permission

sessions_bp = Blueprint("sessions", __name__, url_prefix="/api/sessions")

# In-memory revoke set (also persisted on UserSession.is_revoked)
_REVOKED_JTI = set()


def is_jti_revoked(jti: str) -> bool:
    if not jti:
        return False
    if jti in _REVOKED_JTI:
        return True
    row = UserSession.query.filter_by(jti=jti, is_revoked=True).first()
    return bool(row)


def register_session(user_id: int, jti: str, ip: str = None, ua: str = None):
    if not jti:
        return
    existing = UserSession.query.filter_by(jti=jti).first()
    if existing:
        existing.last_seen_at = datetime.now(timezone.utc)
        db.session.commit()
        return
    db.session.add(UserSession(
        user_id=user_id,
        jti=jti,
        ip_address=ip,
        user_agent=(ua or "")[:255],
    ))
    db.session.commit()


@sessions_bp.route("", methods=["GET"])
@jwt_required()
def list_my_sessions():
    uid = int(get_jwt_identity())
    rows = UserSession.query.filter_by(user_id=uid).order_by(UserSession.created_at.desc()).limit(50).all()
    current = get_jwt().get("jti")
    items = []
    for r in rows:
        d = r.to_dict()
        d["is_current"] = r.jti == current
        items.append(d)
    return jsonify({"items": items, "total": len(items)})


@sessions_bp.route("/user/<int:user_id>", methods=["GET"])
@jwt_required()
@require_permission(Permission.MANAGE_USER)
def list_user_sessions(user_id):
    rows = UserSession.query.filter_by(user_id=user_id).order_by(UserSession.created_at.desc()).limit(50).all()
    return jsonify({"items": [r.to_dict() for r in rows], "total": len(rows)})


@sessions_bp.route("/<int:session_id>/revoke", methods=["POST"])
@jwt_required()
def revoke_session(session_id):
    uid = int(get_jwt_identity())
    me = User.query.get(uid)
    row = UserSession.query.get_or_404(session_id)
    if row.user_id != uid and (not me or me.role != UserRole.ADMIN):
        return jsonify({"error": "Forbidden"}), 403
    row.is_revoked = True
    row.revoked_at = datetime.now(timezone.utc)
    _REVOKED_JTI.add(row.jti)
    db.session.commit()
    AuditLog.log(action="session.revoke", user_id=uid, entity_type="UserSession", entity_id=row.id)
    return jsonify({"message": "Revoked", "session": row.to_dict()})


@sessions_bp.route("/revoke-all", methods=["POST"])
@jwt_required()
def revoke_all_mine():
    uid = int(get_jwt_identity())
    current = get_jwt().get("jti")
    keep_current = (request.get_json() or {}).get("keep_current", True)
    q = UserSession.query.filter_by(user_id=uid, is_revoked=False)
    n = 0
    for row in q.all():
        if keep_current and row.jti == current:
            continue
        row.is_revoked = True
        row.revoked_at = datetime.now(timezone.utc)
        _REVOKED_JTI.add(row.jti)
        n += 1
    db.session.commit()
    return jsonify({"message": f"Revoked {n} sessions"})
