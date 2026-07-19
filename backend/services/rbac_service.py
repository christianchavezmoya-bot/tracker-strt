"""
HOLO-RTLS — Role-Based Access Control (RBAC) Service
Defines the permission matrix and checks user access.
"""
from typing import Set
from backend.models import User, UserRole


# ── Permission Constants ──────────────────────────────────────────────────────
class Permission:
    # Map / Tracking
    VIEW_MAP          = "view_map"
    VIEW_TRACKER      = "view_tracker"

    # Trackers
    MANAGE_TRACKER    = "manage_tracker"     # Create, edit, delete, reassign

    # Zones
    VIEW_ZONE         = "view_zone"
    CREATE_ZONE       = "create_zone"
    EDIT_ZONE         = "edit_zone"
    DELETE_ZONE       = "delete_zone"

    # Alerts
    VIEW_ALERT        = "view_alert"
    ACKNOWLEDGE_ALERT = "acknowledge_alert"

    # Nodes
    MANAGE_NODE       = "manage_node"        # Drag on map, rename, configure

    # History / Reports
    VIEW_HISTORY      = "view_history"
    GENERATE_REPORT   = "generate_report"

    # Users
    MANAGE_USER       = "manage_user"        # Create, edit, deactivate

    # Settings
    VIEW_SETTINGS     = "view_settings"
    EDIT_SETTINGS     = "edit_settings"

    # Audit
    VIEW_AUDIT        = "view_audit"

    # Backup
    TRIGGER_ALARM     = "trigger_alarm"
    TRIGGER_BACKUP    = "trigger_backup"
    RESTORE_BACKUP    = "restore_backup"

    # API Keys
    MANAGE_API_KEY    = "manage_api_key"


# ── Permission Matrix ────────────────────────────────────────────────────────
ROLE_PERMISSIONS: dict[UserRole, Set[str]] = {
    UserRole.VIEWER: {
        Permission.VIEW_MAP,
        Permission.VIEW_TRACKER,
        Permission.VIEW_ZONE,
        Permission.VIEW_ALERT,
        Permission.VIEW_HISTORY,
        Permission.VIEW_SETTINGS,
    },
    UserRole.OPERATOR: {
        Permission.VIEW_MAP,
        Permission.VIEW_TRACKER,
        Permission.MANAGE_TRACKER,
        Permission.VIEW_ZONE,
        Permission.VIEW_ALERT,
        Permission.ACKNOWLEDGE_ALERT,
        Permission.TRIGGER_ALARM,
        Permission.MANAGE_NODE,
        Permission.VIEW_HISTORY,
        Permission.GENERATE_REPORT,
        Permission.VIEW_SETTINGS,
    },
    UserRole.ADMIN: {
        # All permissions
        Permission.VIEW_MAP,
        Permission.VIEW_TRACKER,
        Permission.MANAGE_TRACKER,
        Permission.VIEW_ZONE,
        Permission.CREATE_ZONE,
        Permission.EDIT_ZONE,
        Permission.DELETE_ZONE,
        Permission.VIEW_ALERT,
        Permission.ACKNOWLEDGE_ALERT,
        Permission.TRIGGER_ALARM,
        Permission.MANAGE_NODE,
        Permission.VIEW_HISTORY,
        Permission.GENERATE_REPORT,
        Permission.MANAGE_USER,
        Permission.VIEW_SETTINGS,
        Permission.EDIT_SETTINGS,
        Permission.VIEW_AUDIT,
        Permission.TRIGGER_BACKUP,
        Permission.RESTORE_BACKUP,
        Permission.MANAGE_API_KEY,
    },
}


class RBACService:
    """Singleton service for RBAC checks."""

    def user_has_permission(self, user: User, permission: str) -> bool:
        """Check if a user has a specific permission."""
        if not user or not user.is_active:
            return False
        role_perms = ROLE_PERMISSIONS.get(UserRole(user.role), set())
        return permission in role_perms

    def user_has_any_permission(self, user: User, permissions: list[str]) -> bool:
        """Check if user has at least one of the listed permissions."""
        return any(self.user_has_permission(user, p) for p in permissions)

    def user_has_all_permissions(self, user: User, permissions: list[str]) -> bool:
        """Check if user has all of the listed permissions."""
        return all(self.user_has_permission(user, p) for p in permissions)

    def get_user_permissions(self, user: User) -> list[str]:
        """Return the list of permissions for a user's role."""
        return sorted(ROLE_PERMISSIONS.get(UserRole(user.role), set()))

    def role_has_permission(self, role: UserRole, permission: str) -> bool:
        """Check if a role has a specific permission (static check)."""
        return permission in ROLE_PERMISSIONS.get(role, set())

    def get_role_permissions(self, role: UserRole) -> list[str]:
        """Return all permissions for a given role."""
        return sorted(ROLE_PERMISSIONS.get(role, set()))

    def get_permission_matrix(self) -> dict:
        """
        Return the full permission matrix for admin display.
        Format: { role_name: [permission_list] }
        """
        result = {}
        for role in UserRole:
            result[role.name] = self.get_role_permissions(role)
        return result


# ── Singleton ────────────────────────────────────────────────────────────────
RBAC_SERVICE = RBACService()
