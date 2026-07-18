"""Nodes API — Phase 2 stub."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.models import WifiNode, AuditLog
from backend.utils.decorators import require_permission
from backend.services.rbac_service import Permission

nodes_bp = Blueprint("nodes", __name__, url_prefix="/api/nodes")


@nodes_bp.route("", methods=["GET"])
@jwt_required()
def list_nodes():
    q = WifiNode.query
    if request.args.get("status"):
        q = q.filter_by(status=int(request.args["status"]))
    if request.args.get("node_type"):
        q = q.filter_by(node_type=int(request.args["node_type"]))
    items = q.order_by(WifiNode.id.desc()).all()
    return jsonify({"items": [n.to_dict() for n in items], "total": len(items)})


@nodes_bp.route("", methods=["POST"])
@jwt_required()
@require_permission(Permission.MANAGE_NODE)
def create_node():
    body = request.get_json() or {}
    mac = body.get("mac_address", "").strip()
    if not mac:
        return jsonify({"error": "mac_address is required"}), 400
    if WifiNode.query.filter_by(mac_address=mac).first():
        return jsonify({"error": "mac_address already exists"}), 409
    node = WifiNode(mac_address=mac, assigned_name=body.get("assigned_name"),
                    pos_x=body.get("pos_x", 0), pos_y=body.get("pos_y", 0),
                    pos_z=body.get("pos_z", 0))
    db.session.add(node)
    db.session.commit()
    AuditLog.log(action="node.create", user_id=int(get_jwt_identity()),
                 entity_type="WifiNode", entity_id=node.id)
    return jsonify({"node": node.to_dict()}), 201


@nodes_bp.route("/<int:node_id>", methods=["GET"])
@jwt_required()
def get_node(node_id):
    node = WifiNode.query.get_or_404(node_id)
    return jsonify({"node": node.to_dict()})


@nodes_bp.route("/<int:node_id>", methods=["PATCH"])
@jwt_required()
@require_permission(Permission.MANAGE_NODE)
def update_node(node_id):
    node = WifiNode.query.get_or_404(node_id)
    body = request.get_json() or {}
    for field in ["assigned_name", "pos_x", "pos_y", "pos_z", "node_type",
                   "status", "metadata_json"]:
        if field in body:
            setattr(node, field, body[field])
    db.session.commit()
    AuditLog.log(action="node.update", user_id=int(get_jwt_identity()),
                 entity_type="WifiNode", entity_id=node.id)
    return jsonify({"node": node.to_dict()})


@nodes_bp.route("/<int:node_id>", methods=["DELETE"])
@jwt_required()
@require_permission(Permission.MANAGE_NODE)
def delete_node(node_id):
    node = WifiNode.query.get_or_404(node_id)
    AuditLog.log(action="node.delete", user_id=int(get_jwt_identity()),
                 entity_type="WifiNode", entity_id=node.id)
    db.session.delete(node)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200
