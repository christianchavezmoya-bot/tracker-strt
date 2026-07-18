"""Notifications API — Phase 6 stub."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.models import Notification

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@notifications_bp.route("", methods=["GET"])
@jwt_required()
def list_notifications():
    user_id = int(get_jwt_identity())
    unread_only = request.args.get("unread_only", "false") == "true"
    q = Notification.query.filter_by(user_id=user_id)
    if unread_only:
        q = q.filter_by(is_read=False)
    items = q.order_by(Notification.created_at.desc()).limit(100).all()
    unread_count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    return jsonify({
        "items": [n.to_dict() for n in items],
        "unread_count": unread_count,
    })


@notifications_bp.route("/<int:notification_id>/read", methods=["POST"])
@jwt_required()
def mark_read(notification_id):
    notif = Notification.query.filter_by(
        id=notification_id, user_id=int(get_jwt_identity())
    ).first_or_404()
    notif.is_read = True
    db.session.commit()
    return jsonify({"notification": notif.to_dict()})


@notifications_bp.route("/read-all", methods=["POST"])
@jwt_required()
def mark_all_read():
    user_id = int(get_jwt_identity())
    Notification.query.filter_by(user_id=user_id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"message": "All marked as read"})
