"""Personnel positions & org sections CRUD."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from backend.extensions import db
from backend.models.org import PersonnelPosition, OrgSection
from backend.utils.decorators import require_permission
from backend.services.rbac_service import Permission

org_bp = Blueprint("org", __name__, url_prefix="/api/settings/org")


@org_bp.route("/positions", methods=["GET"])
@jwt_required()
def list_positions():
    items = PersonnelPosition.query.filter_by(is_active=True).order_by(
        PersonnelPosition.sort_order, PersonnelPosition.name
    ).all()
    return jsonify({"items": [p.to_dict() for p in items]})


@org_bp.route("/positions", methods=["POST"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def create_position():
    body = request.get_json() or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if PersonnelPosition.query.filter_by(name=name).first():
        return jsonify({"error": "Position already exists"}), 409
    p = PersonnelPosition(name=name, sort_order=body.get("sort_order", 0))
    db.session.add(p)
    db.session.commit()
    return jsonify({"position": p.to_dict()}), 201


@org_bp.route("/positions/<int:pid>", methods=["PATCH"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def update_position(pid):
    p = PersonnelPosition.query.get_or_404(pid)
    body = request.get_json() or {}
    if "name" in body and body["name"]:
        p.name = body["name"].strip()
    if "sort_order" in body:
        p.sort_order = int(body["sort_order"])
    if "is_active" in body:
        p.is_active = bool(body["is_active"])
    db.session.commit()
    return jsonify({"position": p.to_dict()})


@org_bp.route("/positions/<int:pid>", methods=["DELETE"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def delete_position(pid):
    p = PersonnelPosition.query.get_or_404(pid)
    p.is_active = False
    db.session.commit()
    return jsonify({"message": "Deactivated"})


@org_bp.route("/sections", methods=["GET"])
@jwt_required()
def list_org_sections():
    items = OrgSection.query.filter_by(is_active=True).order_by(
        OrgSection.sort_order, OrgSection.name
    ).all()
    return jsonify({"items": [s.to_dict() for s in items]})


@org_bp.route("/sections", methods=["POST"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def create_org_section():
    body = request.get_json() or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if OrgSection.query.filter_by(name=name).first():
        return jsonify({"error": "Section already exists"}), 409
    s = OrgSection(name=name, sort_order=body.get("sort_order", 0))
    db.session.add(s)
    db.session.commit()
    return jsonify({"section": s.to_dict()}), 201


@org_bp.route("/sections/<int:sid>", methods=["PATCH"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def update_org_section(sid):
    s = OrgSection.query.get_or_404(sid)
    body = request.get_json() or {}
    if "name" in body and body["name"]:
        s.name = body["name"].strip()
    if "sort_order" in body:
        s.sort_order = int(body["sort_order"])
    if "is_active" in body:
        s.is_active = bool(body["is_active"])
    db.session.commit()
    return jsonify({"section": s.to_dict()})


@org_bp.route("/sections/<int:sid>", methods=["DELETE"])
@jwt_required()
@require_permission(Permission.EDIT_SETTINGS)
def delete_org_section(sid):
    s = OrgSection.query.get_or_404(sid)
    s.is_active = False
    db.session.commit()
    return jsonify({"message": "Deactivated"})
