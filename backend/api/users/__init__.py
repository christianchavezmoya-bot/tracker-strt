"""Users Management API — Phase 7 Admin & User Management."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.models import User, UserRole, AuditLog
from backend.utils.decorators import require_permission, admin_only
from backend.services.rbac_service import Permission

users_bp = Blueprint("users", __name__, url_prefix="/api/users")


@users_bp.route("", methods=["POST"])
@jwt_required()
@admin_only
def create_user():
    """
    === A
    tags:
      - Users
    summary: Create a new user account
    description: Creates a new user account. Admin only.
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
              format: email
              description: User email address
            password:
              type: string
              format: password
              description: Password (min 8 characters)
            username:
              type: string
              description: Unique username
            display_name:
              type: string
              description: Display name
            role:
              type: integer
              default: 1
              description: User role (0=ADMIN, 1=OPERATOR, 2=VIEWER)
    responses:
      201:
        description: User created
        schema:
          type: object
          properties:
            user: { type: object }
      400:
        description: Validation error
      409:
        description: Email or username already exists
    ===
    """
    from backend.services.auth_service import AuthService
    body = request.get_json() or {}
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    username = body.get("username", "").strip()
    display_name = body.get("display_name", "").strip()
    role = int(body.get("role", UserRole.OPERATOR))

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409
    if username and User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already taken"}), 409

    svc = AuthService()
    try:
        user = svc.create_user(
            email=email,
            password=password,
            username=username or None,
            display_name=display_name or None,
            role=role,
        )
        AuditLog.log(action="user.create", user_id=int(get_jwt_identity()),
                     entity_type="User", entity_id=user.id,
                     details=f'{{"email": "{email}", "role": "{UserRole(role).name}"}}')
        return jsonify({"user": user.to_dict(include_email=True)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@users_bp.route("", methods=["GET"])
@jwt_required()
@admin_only
def list_users():
    """
    === A
    tags:
      - Users
    summary: List all users
    description: Returns all users with optional filtering by role and active status. Admin only.
    security:
      - Bearer: []
    parameters:
      - in: query
        name: role
        schema:
          type: integer
        description: Filter by role
      - in: query
        name: is_active
        schema:
          type: string
          enum: [true, false]
        description: Filter by active status
    responses:
      200:
        description: List of users
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
            total: { type: integer }
    ===
    """
    q = User.query
    if request.args.get("role"):
        q = q.filter_by(role=int(request.args["role"]))
    if request.args.get("is_active"):
        q = q.filter_by(is_active=request.args["is_active"] == "true")
    items = q.order_by(User.created_at.desc()).all()
    return jsonify({"items": [u.to_dict(include_email=True) for u in items],
                    "total": len(items)})


@users_bp.route("/<int:user_id>", methods=["PATCH"])
@jwt_required()
@admin_only
def update_user(user_id):
    """
    === A
    tags:
      - Users
    summary: Update a user
    description: Updates user details. Admin only.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: user_id
        required: true
        schema:
          type: integer
        description: User ID
      - in: body
        name: body
        schema:
          type: object
          properties:
            username: { type: string }
            display_name: { type: string }
            role: { type: integer }
            is_active: { type: boolean }
    responses:
      200:
        description: User updated
        schema:
          type: object
          properties:
            user: { type: object }
      404:
        description: User not found
    ===
    """
    user = User.query.get_or_404(user_id)
    body = request.get_json() or {}
    for field in ["username", "display_name", "role", "is_active", "phone"]:
        if field in body:
            setattr(user, field, body[field])
    if "notify_prefs" in body:
        import json
        prefs = body["notify_prefs"]
        user.notify_prefs = json.dumps(prefs) if isinstance(prefs, dict) else prefs
    if body.get("password"):
        if len(body["password"]) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400
        user.set_password(body["password"])
    db.session.commit()
    AuditLog.log(action="user.update", user_id=int(get_jwt_identity()),
                 entity_type="User", entity_id=user.id)
    return jsonify({"user": user.to_dict(include_email=True)})


@users_bp.route("/<int:user_id>", methods=["DELETE"])
@jwt_required()
@admin_only
def deactivate_user(user_id):
    """
    === A
    tags:
      - Users
    summary: Deactivate a user
    description: Deactivates a user account. Admin only. Cannot deactivate yourself.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: user_id
        required: true
        schema:
          type: integer
        description: User ID
    responses:
      200:
        description: User deactivated
        schema:
          type: object
          properties:
            message: { type: string }
      400:
        description: Cannot deactivate yourself
      404:
        description: User not found
    ===
    """
    user = User.query.get_or_404(user_id)
    if user.id == int(get_jwt_identity()):
        return jsonify({"error": "Cannot deactivate yourself"}), 400
    user.is_active = False
    db.session.commit()
    AuditLog.log(action="user.deactivate", user_id=int(get_jwt_identity()),
                 entity_type="User", entity_id=user.id)
    return jsonify({"message": "Deactivated"})
