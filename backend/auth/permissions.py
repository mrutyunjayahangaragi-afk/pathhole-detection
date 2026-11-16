"""
Permissions and Access Control Middleware
=========================================
Fine-grained permission and role enforcement decorators.
"""

from functools import wraps
from typing import Callable, Any
from flask import request, jsonify, g
from backend.auth import get_current_user
from backend.database.session import get_db_session
from backend.database.repositories.role_repository import RoleRepository


def permission_required(permission_name: str) -> Callable:
    """Decorator requiring that the authenticated user possesses a specific permission."""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            user = get_current_user()
            if not user:
                return jsonify({
                    "error": "Authentication required. Please log in.",
                    "code": "UNAUTHORIZED"
                }), 401

            session = get_db_session()
            try:
                role_repo = RoleRepository(session)
                if not role_repo.has_permission(user, permission_name):
                    return jsonify({
                        "error": f"Access denied. Missing permission: '{permission_name}'.",
                        "code": "FORBIDDEN"
                    }), 403
            finally:
                session.close()

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def department_scoped(department_id_param: str = "department_id") -> Callable:
    """Decorator verifying that an officer or admin has jurisdiction over the specified department."""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            user = get_current_user()
            if not user:
                return jsonify({"error": "Authentication required.", "code": "UNAUTHORIZED"}), 401

            dept_id = kwargs.get(department_id_param) or request.args.get(department_id_param)
            if not dept_id:
                data = request.get_json(silent=True) or {}
                dept_id = data.get(department_id_param)

            if dept_id:
                session = get_db_session()
                try:
                    role_repo = RoleRepository(session)
                    if not role_repo.can_access_department(user, dept_id):
                        return jsonify({
                            "error": "Access denied. You do not have jurisdiction over this department.",
                            "code": "FORBIDDEN"
                        }), 403
                finally:
                    session.close()

            return f(*args, **kwargs)
        return decorated_function
    return decorator
