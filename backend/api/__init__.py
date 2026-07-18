"""
HOLO-RTLS — Auth API Routes
POST /api/auth/register  — Create account (admin only or open registration)
POST /api/auth/login     — Login (returns JWT)
POST /api/auth/logout    — Logout (audit)
POST /api/auth/2fa/setup — Start 2FA setup
POST /api/auth/2fa/confirm — Confirm 2FA
POST /api/auth/2fa/disable — Disable 2FA
POST /api/auth/refresh   — Refresh access token
POST /api/auth/password/reset-request — Request password reset email
POST /api/auth/password/reset — Reset password with token
GET  /api/auth/me        — Get current user profile
GET  /api/auth/permissions — Get current user's permissions
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    jwt_required, get_jwt_identity, get_jwt,
)
from backend.services.auth_service import AUTH_SERVICE
from backend.services.rbac_service import RBAC_SERVICE
from backend.utils.decorators import require_permission
from backend.models import User, UserRole, AuditLog

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ── Register ──────────────────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Create a new user account.
    Open to anyone in dev mode; in production, restrict to admin-initiated invites.
    """
    body = request.get_json() or {}
    email = body.get("email", "").strip()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    display_name = body.get("display_name", "").strip() or None
    role = int(body.get("role", UserRole.VIEWER))

    if not all([email, username, password]):
        return jsonify({"error": "email, username, and password are required"}), 400

    # Only admins can create non-VIEWER accounts
    try:
        role_enum = UserRole(role)
    except ValueError:
        return jsonify({"error": "Invalid role"}), 400

    # In production, only admin can register new users (enforce via token)
    from backend.config import DEBUG
    if not DEBUG:
        try:
            verify_jwt_in_request(optional=True)
            identity = get_jwt_identity()
            if not identity:
                return jsonify({"error": "Registration is admin-only in production"}), 403
            admin = User.query.get(int(identity))
            if not admin or admin.role != UserRole.ADMIN:
                return jsonify({"error": "Admin access required"}), 403
        except Exception:
            return jsonify({"error": "Authentication required"}), 401

    user, err = AUTH_SERVICE.register(
        email=email,
        username=username,
        password=password,
        role=role,
        display_name=display_name,
        created_by_id=int(get_jwt_identity()) if not DEBUG else None,
    )

    if err:
        return jsonify({"error": err}), 400

    return jsonify({"message": "User created", "user": user.to_dict()}), 201


# ── Login ────────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate and return JWT tokens."""
    body = request.get_json() or {}
    email_or_username = body.get("email_or_username", "").strip()
    password = body.get("password", "")
    totp_code = body.get("totp_code")   # Optional; required if 2FA enabled

    if not all([email_or_username, password]):
        return jsonify({"error": "email_or_username and password are required"}), 400

    result, err = AUTH_SERVICE.login(
        email_or_username=email_or_username,
        password=password,
        totp_code=totp_code,
        ip_address=request.remote_addr,
    )

    if err:
        return jsonify({"error": err}), 401

    if result.get("requires_2fa"):
        return jsonify({
            "requires_2fa": True,
            "user_id": result["user_id"],
            "message": "2FA code required",
        }), 403

    return jsonify({
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "user": result["user"],
    }), 200


# ── Logout ────────────────────────────────────────────────────────────────────
@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    user_id = int(get_jwt_identity())
    AUTH_SERVICE.logout(user_id, ip_address=request.remote_addr)
    return jsonify({"message": "Logged out"}), 200


# ── Token Refresh ─────────────────────────────────────────────────────────────
@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    new_token = AUTH_SERVICE.refresh_access_token(user_id)
    return jsonify({"access_token": new_token}), 200


# ── 2FA Setup ────────────────────────────────────────────────────────────────
@auth_bp.route("/2fa/setup", methods=["POST"])
@jwt_required()
def setup_2fa():
    user_id = int(get_jwt_identity())
    qr_b64, err = AUTH_SERVICE.setup_2fa(user_id)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({
        "qr_code": f"data:image/png;base64,{qr_b64}",
        "message": "Scan the QR code with your authenticator app, then call /2fa/confirm",
    }), 200


@auth_bp.route("/2fa/confirm", methods=["POST"])
@jwt_required()
def confirm_2fa():
    user_id = int(get_jwt_identity())
    body = request.get_json() or {}
    totp_code = body.get("totp_code", "").strip()

    if not totp_code:
        return jsonify({"error": "totp_code is required"}), 400

    ok, err = AUTH_SERVICE.confirm_2fa(user_id, totp_code)
    if not ok:
        return jsonify({"error": err}), 400

    return jsonify({"message": "2FA enabled successfully"}), 200


@auth_bp.route("/2fa/disable", methods=["POST"])
@jwt_required()
def disable_2fa():
    user_id = int(get_jwt_identity())
    body = request.get_json() or {}
    password = body.get("password", "")
    totp_code = body.get("totp_code", "").strip()

    ok, err = AUTH_SERVICE.disable_2fa(user_id, password, totp_code)
    if not ok:
        return jsonify({"error": err}), 400

    return jsonify({"message": "2FA disabled"}), 200


# ── Password Reset ────────────────────────────────────────────────────────────
@auth_bp.route("/password/reset-request", methods=["POST"])
def reset_request():
    body = request.get_json() or {}
    email = body.get("email", "").strip()
    if not email:
        return jsonify({"error": "email is required"}), 400

    AUTH_SERVICE.request_password_reset(email, ip_address=request.remote_addr)
    # Always return 200 — don't reveal if email exists
    return jsonify({"message": "If that email is registered, a reset link has been sent"}), 200


@auth_bp.route("/password/reset", methods=["POST"])
def reset_password():
    body = request.get_json() or {}
    token = body.get("token", "")
    new_password = body.get("new_password", "")

    if not all([token, new_password]):
        return jsonify({"error": "token and new_password are required"}), 400

    ok, err = AUTH_SERVICE.reset_password(token, new_password)
    if not ok:
        return jsonify({"error": err}), 400

    return jsonify({"message": "Password reset successfully"}), 200


# ── Current User ─────────────────────────────────────────────────────────────
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user": user.to_dict(include_email=True)}), 200


@auth_bp.route("/permissions", methods=["GET"])
@jwt_required()
def permissions():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "role": user.role_name,
        "permissions": RBAC_SERVICE.get_user_permissions(user),
    }), 200
