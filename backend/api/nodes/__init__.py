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
    === A
    tags:
      - Nodes
    summary: List all WiFi nodes
    description: Returns all WiFi nodes with optional filtering by status and type.
    security:
      - Bearer: []
    parameters:
      - in: query
        name: status
        schema:
          type: integer
        description: Filter by node status
      - in: query
        name: node_type
        schema:
          type: integer
        description: Filter by node type
    responses:
      200:
        description: List of WiFi nodes
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
            total: { type: integer }
    ===
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
    === A
    tags:
      - Nodes
    summary: Create a WiFi node
    description: Creates a new WiFi node. Requires MANAGE_NODE permission.
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - mac_address
          properties:
            mac_address:
              type: string
              description: MAC address of the node
            assigned_name:
              type: string
              description: Human-readable name
            pos_x:
              type: number
              default: 0
              description: X coordinate
            pos_y:
              type: number
              default: 0
              description: Y coordinate
            pos_z:
              type: number
              default: 0
              description: Z coordinate
    responses:
      201:
        description: Node created
        schema:
          type: object
          properties:
            node: { type: object }
      400:
        description: mac_address is required
      409:
        description: MAC address already exists
    ===
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
    === A
    tags:
      - Nodes
    summary: Get a WiFi node
    description: Returns details for a specific WiFi node.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: node_id
        required: true
        schema:
          type: integer
        description: Node ID
    responses:
      200:
        description: Node details
        schema:
          type: object
          properties:
            node: { type: object }
      404:
        description: Node not found
    ===
    node = WifiNode.query.get_or_404(node_id)
    return jsonify({"node": node.to_dict()})


@nodes_bp.route("/<int:node_id>", methods=["PATCH"])
@jwt_required()
@require_permission(Permission.MANAGE_NODE)
def update_node(node_id):
    === A
    tags:
      - Nodes
    summary: Update a WiFi node
    description: Updates a WiFi node. Requires MANAGE_NODE permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: node_id
        required: true
        schema:
          type: integer
        description: Node ID
      - in: body
        name: body
        schema:
          type: object
          properties:
            assigned_name: { type: string }
            pos_x: { type: number }
            pos_y: { type: number }
            pos_z: { type: number }
            node_type: { type: integer }
            status: { type: integer }
            metadata_json: { type: string }
    responses:
      200:
        description: Node updated
        schema:
          type: object
          properties:
            node: { type: object }
      404:
        description: Node not found
    ===
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
    === A
    tags:
      - Nodes
    summary: Delete a WiFi node
    description: Deletes a WiFi node. Requires MANAGE_NODE permission.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: node_id
        required: true
        schema:
          type: integer
        description: Node ID
    responses:
      200:
        description: Node deleted
        schema:
          type: object
          properties:
            message: { type: string }
      404:
        description: Node not found
    ===
    node = WifiNode.query.get_or_404(node_id)
    AuditLog.log(action="node.delete", user_id=int(get_jwt_identity()),
                 entity_type="WifiNode", entity_id=node.id)
    db.session.delete(node)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200
