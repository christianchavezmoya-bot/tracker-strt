"""Web Push subscription API (VAPID)."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from backend.extensions import db
from backend.models.integrations import PushSubscription
from backend import config

push_bp = Blueprint("push", __name__, url_prefix="/api/push")


@push_bp.route("/vapid-public-key", methods=["GET"])
@jwt_required()
def vapid_public_key():
    """Return VAPID public key for PushManager.subscribe()."""
    return jsonify({
        "configured": bool(config.WEB_PUSH_ENABLED),
        "public_key": config.VAPID_PUBLIC_KEY or None,
    })


@push_bp.route("/subscribe", methods=["POST"])
@jwt_required()
def subscribe():
    """Register or update a browser push subscription for the current user."""
    body = request.get_json() or {}
    endpoint = (body.get("endpoint") or "").strip()
    keys = body.get("keys") or {}
    p256dh = keys.get("p256dh") or body.get("p256dh")
    auth_key = keys.get("auth") or body.get("auth")
    if not endpoint or not p256dh or not auth_key:
        return jsonify({"error": "endpoint and keys.p256dh, keys.auth are required"}), 400

    user_id = int(get_jwt_identity())
    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if sub:
        sub.user_id = user_id
        sub.p256dh = p256dh
        sub.auth = auth_key
        sub.user_agent = (request.headers.get("User-Agent") or "")[:500]
    else:
        sub = PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth_key,
            user_agent=(request.headers.get("User-Agent") or "")[:500],
        )
        db.session.add(sub)
    db.session.commit()
    return jsonify({"message": "Subscribed", "subscription": sub.to_dict()}), 201


@push_bp.route("/subscribe", methods=["DELETE"])
@jwt_required()
def unsubscribe():
    """Remove a push subscription (by endpoint or all for current user)."""
    user_id = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    endpoint = (body.get("endpoint") or request.args.get("endpoint") or "").strip()
    if endpoint:
        sub = PushSubscription.query.filter_by(endpoint=endpoint, user_id=user_id).first()
        if sub:
            db.session.delete(sub)
            db.session.commit()
        return jsonify({"message": "Unsubscribed"})
    deleted = PushSubscription.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    return jsonify({"message": "Unsubscribed", "removed": deleted})


@push_bp.route("/subscriptions", methods=["GET"])
@jwt_required()
def list_subscriptions():
    """List current user's push subscriptions (masked endpoints)."""
    user_id = int(get_jwt_identity())
    items = PushSubscription.query.filter_by(user_id=user_id).all()
    return jsonify({"items": [s.to_dict() for s in items], "configured": bool(config.WEB_PUSH_ENABLED)})
