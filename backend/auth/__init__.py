"""
CivicLens Modular Authentication Package
========================================
Combines session/bearer authentication, Supabase Auth integration,
and fine-grained role-based permissions.
"""

from backend.auth_compat import (
    get_token_serializer,
    generate_auth_token,
    verify_auth_token,
    get_current_user,
    login_required,
    role_required,
)
from backend.auth.permissions import permission_required, department_scoped
from backend.auth.supabase_auth import SupabaseAuthService
from backend.auth.invitations import create_invitation, verify_invitation, accept_invitation

__all__ = [
    "get_token_serializer",
    "generate_auth_token",
    "verify_auth_token",
    "get_current_user",
    "login_required",
    "role_required",
    "permission_required",
    "department_scoped",
    "SupabaseAuthService",
    "create_invitation",
    "verify_invitation",
    "accept_invitation",
]
