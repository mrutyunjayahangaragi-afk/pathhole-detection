"""
Role & Permission Repository
============================
Enforces role-based permissions and hierarchical capabilities across CivicLens.
"""

from typing import Set, Optional
from sqlalchemy.orm import Session
from backend.db.models import User, DepartmentMembership

ROLE_PERMISSIONS = {
    "citizen": {
        "report_defect",
        "view_own_reports",
        "track_own_reports",
        "view_public_map",
        "follow_incident",
    },
    "municipal_officer": {
        "view_incident",
        "verify_incident",
        "record_inspection",
        "update_work_progress",
        "upload_resolution_evidence",
        "view_assigned_department",
    },
    "dept_admin": {
        "view_incident",
        "verify_incident",
        "assign_incident",
        "record_inspection",
        "update_work_progress",
        "approve_resolution",
        "invite_officer",
        "view_department_metrics",
        "manage_department_officers",
    },
    "municipal_admin": {
        "view_incident",
        "verify_incident",
        "assign_incident",
        "manage_department",
        "invite_officer",
        "manage_users",
        "approve_resolution",
        "view_audit_logs",
        "view_all_departments",
    },
    "system_admin": {
        "view_incident",
        "verify_incident",
        "assign_incident",
        "manage_department",
        "invite_officer",
        "manage_users",
        "manage_municipalities",
        "approve_resolution",
        "view_audit_logs",
        "system_configuration",
    },
}


class RoleRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_user_permissions(self, user: User) -> Set[str]:
        """Returns the set of permissions granted to a user based on their active role."""
        if not user or not user.is_active:
            return set()
        return ROLE_PERMISSIONS.get(user.role, set())

    def has_permission(self, user: User, permission: str) -> bool:
        """Checks if a user has a specific permission."""
        if not user or not user.is_active:
            return False
        return permission in self.get_user_permissions(user)

    def can_access_department(self, user: User, department_id: str) -> bool:
        """Verifies if an official can access data scoped to a specific department."""
        if not user or not user.is_active:
            return False
        if user.role in ("system_admin", "municipal_admin"):
            return True
        membership = self.session.query(DepartmentMembership).filter_by(
            user_id=user.id, department_id=department_id, is_active=True
        ).first()
        return membership is not None
