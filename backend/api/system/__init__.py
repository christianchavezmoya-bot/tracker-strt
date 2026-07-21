"""System status APIs — RTLS readiness, MQTT broker control."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from backend.extensions import db
from backend.models import AuditLog
from backend.services.rbac_service import Permission
from backend.services.rtls_readiness import compute_readiness
from backend.services.mqtt_broker_manager import (
    apply_broker_enabled,
    broker_status_summary,
    is_broker_enabled,
    set_broker_enabled,
    wifi_unit_setup_info,
)
from backend.utils.decorators import require_permission

system_bp = Blueprint("system", __name__, url_prefix="/api/system")


@system_bp.route("/rtls-readiness", methods=["GET"])
@jwt_required()
def rtls_readiness():
    """Commissioning checklist for Live Map tag visibility."""
    return jsonify(compute_readiness(db.session))


@system_bp.route("/wifi-unit-setup", methods=["GET"])
@jwt_required()
def wifi_unit_setup():
    """Copy-paste settings card for configuring WiFi scanner units."""
    host = request.headers.get("X-Forwarded-Host") or request.host
    return jsonify(wifi_unit_setup_info(host))


@system_bp.route("/mqtt-broker", methods=["GET"])
@jwt_required()
def mqtt_broker_status():
    return jsonify(broker_status_summary())


@system_bp.route("/mqtt-broker", methods=["POST"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def mqtt_broker_control():
    """
    Enable or disable the embedded MQTT broker at runtime.
    Body: { "enabled": true|false }
    """
    body = request.get_json() or {}
    if "enabled" not in body:
        return jsonify({"error": "enabled is required"}), 400

    enabled = bool(body["enabled"])
    user_id = int(get_jwt_identity())
    set_broker_enabled(enabled, user_id=user_id)
    result = apply_broker_enabled(enabled)
    AuditLog.log(
        action="system.mqtt_broker",
        user_id=user_id,
        entity_type="Setting",
        details=f'{{"enabled": {str(enabled).lower()}}}',
    )
    return jsonify(result)
