"""
HOLO-RTLS — Route Decorators
@require_permission, @rate_limit, @audit_log, etc.
"""
from functools import wraps
from flask import jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

from backend.models import User
from backend.services.rbac_service import RBAC_SERVICE


def require_permission(*permissions):
    """
    Require one or more permissions to access the route.
    Use:  @require_permission(Permission.MANAGE_TRACKER)
          @require_permission(Permission.VIEW_AUDIT, Permission.VIEW_SETTINGS)
    Multiple args = user must have ALL of them (AND logic).
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            user = User.query.get(int(user_id))

            if not user:
                return jsonify({"error": "User not found"}), 404
            if not user.is_active:
                return jsonify({"error": "Account deactivated"}), 403

            # Check all required permissions (AND logic)
            for perm in permissions:
                if not RBAC_SERVICE.user_has_permission(user, perm):
                    return jsonify({
                        "error": "Forbidden",
                        "message": f"You don't have the '{perm}' permission",
                    }), 403

            # Attach user to request context for route handlers
            request.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_any_permission(*permissions):
    """
    Require at least one of the listed permissions (OR logic).
    Use:  @require_any_permission(Permission.VIEW_ALERT, Permission.VIEW_AUDIT)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            user = User.query.get(int(user_id))

            if not user or not user.is_active:
                return jsonify({"error": "Unauthorized"}), 401

            if not RBAC_SERVICE.user_has_any_permission(user, list(permissions)):
                return jsonify({"error": "Forbidden"}), 403

            request.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_only(f):
    """Shortcut: require ADMIN role."""
    from backend.models import UserRole
    @wraps(f)
    def decorated_function(*args, **kwargs):
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user or not user.is_active:
            return jsonify({"error": "Unauthorized"}), 401
        if user.role != UserRole.ADMIN:
            return jsonify({"error": "Admin access required"}), 403
        request.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def audit_log(action: str, entity_type: str = None, entity_id_from: str = None):
    """
    Decorator: automatically log an audit entry after a successful route handler.
    entity_id_from: name of route argument to extract as entity_id.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            result = f(*args, **kwargs)

            # Only log successful responses (2xx)
            if isinstance(result, tuple):
                response_data, status_code = result[0], result[1]
            else:
                response_data, status_code = result, 200

            if status_code < 200 or status_code >= 300:
                return result

            # Extract entity_id from route kwargs if specified
            entity_id = None
            if entity_id_from and entity_id_from in kwargs:
                entity_id = kwargs[entity_id_from]

            # Get user from request context
            try:
                verify_jwt_in_request(optional=True)
                user_id = get_jwt_identity()
            except Exception:
                user_id = None

            from backend.models import AuditLog as AuditLogModel
            from backend.extensions import db

            AuditLogModel.log(
                action=action,
                user_id=int(user_id) if user_id else None,
                entity_type=entity_type,
                entity_id=entity_id,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string[:200] if request.user_agent else None,
            )

            return result
        return decorated_function
    return decorator


def rate_limit(calls: int = 60, period: int = 60):
    """
    Simple in-memory rate limiter (use Redis for production multi-instance).
    Args:
        calls: max requests allowed per period
        period: period in seconds
    """
    import time
    from threading import Lock

    _storage: dict[str, list[float]] = {}
    _lock = Lock()

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            key = f"{request.remote_addr}:{request.endpoint}"
            now = time.time()

            with _lock:
                # Clean old entries
                if key in _storage:
                    _storage[key] = [t for t in _storage[key] if now - t < period]
                else:
                    _storage[key] = []

                if len(_storage[key]) >= calls:
                    return jsonify({
                        "error": "Rate limit exceeded",
                        "retry_after": int(period - (now - _storage[key][0])) + 1,
                    }), 429

                _storage[key].append(now)

            return f(*args, **kwargs)
        return decorated_function
    return decorator
