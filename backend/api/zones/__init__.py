"""Zones + Sections API — Phase 2 stub."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.models import Zone, MapSection, AuditLog
from backend.models.tracker import ZoneType
from backend.utils.decorators import require_permission
from backend.services.rbac_service import Permission

zones_bp = Blueprint("zones", __name__, url_prefix="/api/zones")


def _parse_zone_type(raw, default=ZoneType.NORMAL) -> int:
    """Accept int, numeric string, or enum name (e.g. RESTRICTED)."""
    if raw is None or raw == "":
        return int(default)
    if isinstance(raw, int):
        try:
            return int(ZoneType(raw))
        except ValueError:
            return int(default)
    s = str(raw).strip()
    if s.isdigit():
        try:
            return int(ZoneType(int(s)))
        except ValueError:
            return int(default)
    try:
        return int(ZoneType[s.upper()])
    except KeyError:
        return int(default)

@zones_bp.route("/sections", methods=["GET"])
@jwt_required()
def list_sections():
    """
    === A
    tags:
      - Zones
    summary: List all map sections
    description: Returns all map sections ordered by z-index.
    security:
      - Bearer: []
    responses:
      200:
        description: List of sections
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
    ===
    """
    items = MapSection.query.order_by(MapSection.z_index).all()
    return jsonify({"items": [s.to_dict() for s in items]})


@zones_bp.route("/sections", methods=["POST"])
@jwt_required()
@require_permission(Permission.CREATE_ZONE)
def create_section():
    """
    === A
    tags:
      - Zones
    summary: Create a map section
    description: Creates a new map section (polygon area). Requires CREATE_ZONE permission.
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - name
          properties:
            name:
              type: string
              description: Section name
            polygon:
              type: array
              description: Array of polygon vertex coordinates
            is_restricted:
              type: boolean
              default: false
              description: Whether the section is restricted
            is_visible:
              type: boolean
              default: true
            color_hex:
              type: string
              default: "#00e5ff"
              description: Hex color code
            z_index:
              type: integer
              default: 0
              description: Layer order
    responses:
      201:
        description: Section created
        schema:
          type: object
          properties:
            section: { type: object }
      400:
        description: Name is required
    ===
    """
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
    """
    === A
    tags:
      - Zones
    summary: Update a map section
    description: Updates an existing map section. Requires EDIT_ZONE permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: section_id
        required: true
        schema:
          type: integer
        description: Section ID
      - in: body
        name: body
        schema:
          type: object
          properties:
            name: { type: string }
            polygon_json: { type: string }
            is_restricted: { type: boolean }
            is_visible: { type: boolean }
            color_hex: { type: string }
            z_index: { type: integer }
    responses:
      200:
        description: Section updated
        schema:
          type: object
          properties:
            section: { type: object }
      404:
        description: Section not found
    ===
    """
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
    """
    === A
    tags:
      - Zones
    summary: Delete a map section
    description: Deletes a map section. Requires DELETE_ZONE permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: section_id
        required: true
        schema:
          type: integer
        description: Section ID
    responses:
      200:
        description: Section deleted
        schema:
          type: object
          properties:
            message: { type: string }
      404:
        description: Section not found
    ===
    """
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
    """
    === A
    tags:
      - Zones
    summary: List all zones
    description: Returns all zones in the system.
    security:
      - Bearer: []
    responses:
      200:
        description: List of zones
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
    ===
    """
    items = Zone.query.all()
    return jsonify({"items": [z.to_dict() for z in items]})


@zones_bp.route("", methods=["POST"])
@jwt_required()
@require_permission(Permission.CREATE_ZONE)
def create_zone():
    """
    === A
    tags:
      - Zones
    summary: Create a zone
    description: Creates a new zone (circular area). Requires CREATE_ZONE permission.
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        schema:
          type: object
          properties:
            name:
              type: string
              default: "Unnamed Zone"
              description: Zone name
            zone_type:
              type: integer
              default: 1
              description: Zone type classification
            pos_x:
              type: number
              default: 0
              description: X center coordinate
            pos_y:
              type: number
              default: 0
              description: Y center coordinate
            pos_z:
              type: number
              default: 0
              description: Z center coordinate (elevation)
            radius:
              type: number
              default: 5
              description: Zone radius in meters
            is_visible:
              type: boolean
              default: true
            color_hex:
              type: string
              default: "#00e5ff"
            section_id:
              type: integer
              description: Associated section ID
    responses:
      201:
        description: Zone created
        schema:
          type: object
          properties:
            zone: { type: object }
    ===
    """
    body = request.get_json() or {}
    zone = Zone(
        name=body.get("name", "").strip() or "Unnamed Zone",
        zone_type=_parse_zone_type(body.get("zone_type", 1)),
        pos_x=float(body.get("pos_x", body.get("center_x", 0)) or 0),
        pos_y=float(body.get("pos_y", body.get("center_y", 0)) or 0),
        pos_z=float(body.get("pos_z", 0) or 0),
        radius=float(body.get("radius", 5) or 5),
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
    """
    === A
    tags:
      - Zones
    summary: Update a zone
    description: Updates an existing zone. Requires EDIT_ZONE permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: zone_id
        required: true
        schema:
          type: integer
        description: Zone ID
      - in: body
        name: body
        schema:
          type: object
          properties:
            name: { type: string }
            zone_type: { type: integer }
            pos_x: { type: number }
            pos_y: { type: number }
            pos_z: { type: number }
            radius: { type: number }
            is_visible: { type: boolean }
            color_hex: { type: string }
            section_id: { type: integer }
    responses:
      200:
        description: Zone updated
        schema:
          type: object
          properties:
            zone: { type: object }
      404:
        description: Zone not found
    ===
    """
    zone = Zone.query.get_or_404(zone_id)
    body = request.get_json() or {}
    for field in ["name", "zone_type", "pos_x", "pos_y", "pos_z",
                   "radius", "is_visible", "color_hex", "section_id"]:
        if field in body:
            val = body[field]
            if field == "zone_type":
                val = _parse_zone_type(val)
            setattr(zone, field, val)
    db.session.commit()
    AuditLog.log(action="zone.update", user_id=int(get_jwt_identity()),
                 entity_type="Zone", entity_id=zone.id)
    return jsonify({"zone": zone.to_dict()})


@zones_bp.route("/<int:zone_id>", methods=["DELETE"])
@jwt_required()
@require_permission(Permission.DELETE_ZONE)
def delete_zone(zone_id):
    """
    === A
    tags:
      - Zones
    summary: Delete a zone
    description: Deletes a zone. Requires DELETE_ZONE permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: zone_id
        required: true
        schema:
          type: integer
        description: Zone ID
    responses:
      200:
        description: Zone deleted
        schema:
          type: object
          properties:
            message: { type: string }
      404:
        description: Zone not found
    ===
    """
    zone = Zone.query.get_or_404(zone_id)
    AuditLog.log(action="zone.delete", user_id=int(get_jwt_identity()),
                 entity_type="Zone", entity_id=zone.id)
    db.session.delete(zone)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200
