"""
CivicLens Authentication Compatibility Layer
============================================
Provides token serialization, user resolution, and decorators for Flask endpoints.
"""

from functools import wraps
from typing import Optional, List
from flask import request, session, g, jsonify, current_app
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from backend.db.engine import get_session_factory
from backend.db.models import User


def get_token_serializer() -> URLSafeTimedSerializer:
    """Returns the URLSafeTimedSerializer using the application secret key."""
    try:
        secret = current_app.config.get("SECRET_KEY", "insecure-dev-key")
    except RuntimeError:
        from backend.config import get_config
        secret = get_config().SECRET_KEY
    return URLSafeTimedSerializer(secret_key=secret, salt="civiclens-auth-salt")


def generate_auth_token(user_id: str, role: str) -> str:
    """Generates a cryptographically signed auth token valid for 24 hours."""
    s = get_token_serializer()
    return s.dumps({"sub": user_id, "role": role})


def verify_auth_token(token: str, max_age: int = 86400) -> Optional[dict]:
    """Verifies a signed token and returns the payload dict or None if invalid/expired."""
    s = get_token_serializer()
    try:
        data = s.loads(token, max_age=max_age)
        return data
    except (SignatureExpired, BadSignature):
        return None


def get_current_user() -> Optional[User]:
    """
    Resolves the authenticated user from the active session or Authorization header.
    Bearer tokens take precedence over session cookies.
    """
    if hasattr(g, "current_user") and g.current_user is not None:
        return g.current_user

    user_id = None

    # 1. Check Authorization Bearer header first (takes precedence over cookies)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        payload = verify_auth_token(token)
        if payload:
            user_id = payload.get("sub")

    # 2. Check Flask session cookie fallback
    if not user_id and "user_id" in session:
        user_id = session["user_id"]

    if not user_id:
        g.current_user = None
        return None

    # Load user from database
    SessionFactory = get_session_factory()
    db_session = SessionFactory()
    try:
        user = db_session.query(User).filter_by(id=user_id, is_active=True).first()
        if user:
            db_session.expunge(user)
            g.current_user = user
            return user
    finally:
        db_session.close()

    g.current_user = None
    return None


def login_required(f):
    """Decorator requiring a valid authenticated session or Bearer token."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return jsonify({
                "error": "Authentication required. Please log in.",
                "code": "UNAUTHORIZED"
            }), 401
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles: str):
    """Decorator requiring that the authenticated user possesses one of the allowed roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if user is None:
                return jsonify({
                    "error": "Authentication required. Please log in.",
                    "code": "UNAUTHORIZED"
                }), 401
            if user.role not in allowed_roles:
                return jsonify({
                    "error": "Access denied. Insufficient role permissions.",
                    "code": "FORBIDDEN"
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator
