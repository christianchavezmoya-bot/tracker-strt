"""Zones + Sections API — Phase 2 stub."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.models import Zone, MapSection, AuditLog
from backend.utils.decorators import require_permission
from backend.services.rbac_service import Permission

zones_bp = Blueprint("zones", __name__, url_prefix="/api/zones")


@zones_bp.route("/sections", methods=["GET"])
@jwt_required()
def list_sections():
    items = MapSection.query.order_by(MapSection.z_index).all()
    return jsonify({"items": [s.to_dict() for s in items]})


@zones_bp.route("/sections", methods=["POST"])
@jwt_required()
@require_permission(Permission.CREATE_ZONE)
def create_section():
    body = request.get_json() or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    import json
    section = MapSection(
        name=name,
        polygon_json=json.dumps(body.get("polygon", [])),
        is_restricted=body.get("is_restricted", False),
        is_visible=body.get("is_visible", True),
        color_hex=body.get("color_hex", "#00e5ff"),
        z_index=body.get("z_index", 0),
    )
    db.session.add(section)
    db.session.commit()
    AuditLog.log(action="section.create", user_id=int(get_jwt_identity()),
                 entity_type="MapSection", entity_id=section.id)
    return jsonify({"section": section.to_dict()}), 201


@zones_bp.route("/sections/<int:section_id>", methods=["PATCH"])
@jwt_required()
@require_permission(Permission.EDIT_ZONE)
def update_section(section_id):
    section = MapSection.query.get_or_404(section_id)
    body = request.get_json() or {}
    for field in ["name", "polygon_json", "is_restricted", "is_visible", "color_hex", "z_index"]:
        if field in body:
            setattr(section, field, body[field])
    db.session.commit()
    AuditLog.log(action="section.update", user_id=int(get_jwt_identity()),
                 entity_type="MapSection", entity_id=section.id)
    return jsonify({"section": section.to_dict()})


@zones_bp.route("/sections/<int:section_id>", methods=["DELETE"])
@jwt_required()
@require_permission(Permission.DELETE_ZONE)
def delete_section(section_id):
    section = MapSection.query.get_or_404(section_id)
    AuditLog.log(action="section.delete", user_id=int(get_jwt_identity()),
                 entity_type="MapSection", entity_id=section.id)
    db.session.delete(section)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200


# ── Zones ────────────────────────────────────────────────────────────────────
@zones_bp.route("", methods=["GET"])
@jwt_required()
def list_zones():
    items = Zone.query.all()
    return jsonify({"items": [z.to_dict() for z in items]})


@zones_bp.route("", methods=["POST"])
@jwt_required()
@require_permission(Permission.CREATE_ZONE)
def create_zone():
    body = request.get_json() or {}
    zone = Zone(
        name=body.get("name", "").strip() or "Unnamed Zone",
        zone_type=body.get("zone_type", 1),
        pos_x=body.get("pos_x", 0),
        pos_y=body.get("pos_y", 0),
        pos_z=body.get("pos_z", 0),
        radius=body.get("radius", 5),
        is_visible=body.get("is_visible", True),
        color_hex=body.get("color_hex", "#00e5ff"),
        section_id=body.get("section_id"),
    )
    db.session.add(zone)
    db.session.commit()
    AuditLog.log(action="zone.create", user_id=int(get_jwt_identity()),
                 entity_type="Zone", entity_id=zone.id)
    return jsonify({"zone": zone.to_dict()}), 201


@zones_bp.route("/<int:zone_id>", methods=["PATCH"])
@jwt_required()
@require_permission(Permission.EDIT_ZONE)
def update_zone(zone_id):
    zone = Zone.query.get_or_404(zone_id)
    body = request.get_json() or {}
    for field in ["name", "zone_type", "pos_x", "pos_y", "pos_z",
                   "radius", "is_visible", "color_hex", "section_id"]:
        if field in body:
            setattr(zone, field, body[field])
    db.session.commit()
    AuditLog.log(action="zone.update", user_id=int(get_jwt_identity()),
                 entity_type="Zone", entity_id=zone.id)
    return jsonify({"zone": zone.to_dict()})


@zones_bp.route("/<int:zone_id>", methods=["DELETE"])
@jwt_required()
@require_permission(Permission.DELETE_ZONE)
def delete_zone(zone_id):
    zone = Zone.query.get_or_404(zone_id)
    AuditLog.log(action="zone.delete", user_id=int(get_jwt_identity()),
                 entity_type="Zone", entity_id=zone.id)
    db.session.delete(zone)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200
